"""

Created on '19.05.2015'

@author:'simkaufm'

"""

import logging
import time
import gc
from copy import deepcopy
from datetime import datetime, timedelta

import numpy as np
from PyQt5 import QtWidgets, Qt
from PyQt5.QtCore import QObject, pyqtSignal

import Tilda.Application.Config as Cfg
import Tilda.Driver.COntrolFpga.PulsePatternGenerator as PPG
import Tilda.Driver.COntrolFpga.PulsePatternGeneratorDummy as PPGDummy
import Tilda.Driver.DataAcquisitionFpga.FindSequencerByType as FindSeq
import Tilda.Driver.DigitalMultiMeter.DigitalMultiMeterControl as DmmCtrl

import Tilda.Driver.PostAcceleration.PostAccelerationMain as PostAcc
import Tilda.Service.Scan.ScanDictionaryOperations as SdOp
import Tilda.Service.Scan.draftScanParameters as DftScan
from Tilda.PolliFit import TildaTools as TiTs
from Tilda.Driver.TritonListener.TritonListener import TritonListener

from Tilda.Driver.ScanDevice.TritonScanDevControl import TritonScanDevControl
from Tilda.Service.AnalysisAndDataHandling.AnalysisThread import AnalysisThread as AnalThr
from Tilda.Driver.ScanDevice.BaseTildaScanDeviceControl import BaseTildaScanDeviceControl as BaseScDev
from Tilda.Driver.ScanDevice.AD57X1ScanDevice import AD57X1ScanDev
from Tilda.Driver.ScanDevice.NiUsb6225ScanDevice import NiUsb6225ScanDevice

from Tilda.Application.Importer import InfluxConfig
if InfluxConfig.useinfluxoversql:
    from Tilda.Driver.InfluxStream.InfluxStream import InfluxStream as db_logger
    logging.info("using InfluxDB as database source")
else:
    from Tilda.Driver.SQLStream.SQLStream import SQLStream as db_logger
    logging.info("using SQL as database source")


class ScanMain(QObject):
    # signal to stop the analysis in the analysis thread,
    # first bool is for clearing the pipeline, second bool is for stopping the whole analysis.
    stop_analysis_sig = pyqtSignal(bool, bool)
    # signal to prepare the pipeline for the next track. This will also start the pipe
    prep_track_in_pipe_sig = pyqtSignal(int, int)
    # signal which can be used to send new data to the pipeline.
    # np.ndarray for numpy data, dict for dictionary with dmm readbacks
    # the one you don't need, leave empty (np.ndarray(0, dtype=np.int32) / {})
    data_to_pipe_sig = pyqtSignal(np.ndarray, dict)
    # signal to receive next step requests from fpga
    # the number of the step to be set is included in the send
    scan_dev_step_request_callback = pyqtSignal(int)
    # signal send by the pipeline during a kepco scan, if a new voltage has ben set
    # use this to trigger the dmms if wanted
    dac_new_volt_set_callback = pyqtSignal(int)
    # signal to emit dmm values for live plotting during the pre/post scans.
    # is also used for triton values in TritonListener
    pre_post_meas_data_dict_callback = pyqtSignal(dict)

    def __init__(self):
        super(ScanMain, self).__init__()
        self.sequencer = None
        self.analysis_thread = None
        self.switch_box_is_switched_time = None  # datetime of switching the box.
        self.switch_box_state_before_switch = None  # state before switching
        # for limiting the print of the scan progress
        self.last_scan_prog_update = datetime.now() - timedelta(seconds=10)

        self.post_acc_main = PostAcc.PostAccelerationMain()
        self.digital_multi_meter = DmmCtrl.DMMControl()
        self.dac_new_volt_set_callback.connect(self.rcvd_dac_new_voltage_during_kepco_scan)
        self.dmm_pre_scan_done = False  # bool to use when pre/during/post scan measurement of dmms is completed
        self.dmm_feed_pipe = True

        self.pulse_pattern_gen = None
        self.ground_pin_warned = False
        self.ground_warning_win = None

        # create a triton device for collecting data from other triton devices:
        # self.triton_listener = None
        self.triton_listener_name = 'TildaTritListen'
        self.triton_listener = TritonListener(self.triton_listener_name)
        self.triton_pre_scan_done = False  # bool to use when pre/during/post scan measurement of triton is completed

        # create an SQLStream object for collecting data from a db.
        self.sql_stream = db_logger()  #SQLStream()
        self.sql_pre_scan_done = False  # bool to use when pre/during/post scan measurement of sql stream is completed

        # create a Triton device for controling scans:
        self.triton_scan_controller_name = 'TildaScanDevCtl'
        self.triton_scan_controller = None
        self.triton_scan_controller = TritonScanDevControl(self.triton_scan_controller_name)
        # connect to callback
        self.scan_dev_step_request_callback.connect(self.request_next_step_sc_dev_from_sc_main)
        # only initialise on scan?!

        # create a blank scan device -> will be overwritten by something else that can control a scan device
        self.scan_dev = BaseScDev()

        # needed to prevent emitting of pyqtsignals every 50 ms
        self.incoming_raw_data_storage = np.zeros(0, dtype=np.int32)

        self.datetime_of_last_raw_data_emit = datetime.now()
        self.timedelta_between_raw_data_emits = timedelta(milliseconds=250)


    ''' scan main functions: '''

    def close_scan_main(self):
        """
        will deinitialize all active power supplies,
        set 0V on the DAC and turn off all fpga outputs
        """
        self.deinit_post_accel_pwr_supplies()
        self.deinit_fpga(True)
        self.ppg_deinit(True)
        self.de_init_dmm('all')
        self.stop_triton_listener()
        self.scan_dev.deinit_scan_dev()  # deinit the current scan dev
        try:
            if self.triton_scan_controller is not None and self.triton_scan_controller != self.scan_dev:
                self.triton_scan_controller.deinit_scan_dev()
        except Exception as e:
            logging.error('could not stop TildaTritonScanControl, error is %s' % e, exc_info=True)

    def prepare_scan(self, scan_dict):  # callback_sig=None):
        """
        function to prepare for the scan of one isotope.
        This sets up the pipeline and loads the bitfile on the fpga of the given type.
        """
        if self.analysis_thread:
            # if analysis_thread already exists, delete it
            del self.analysis_thread
        gc.collect()

        # self.analysis_thread should exist!
        self.analysis_thread = None

        t = datetime.today()
        unix_time = time.mktime(t.timetuple())
        scan_dict['pipeInternals']['curVoltInd'] = 0
        scan_dict['isotopeData']['isotopeStartTime'] = t.strftime('%Y-%m-%d %H:%M:%S')
        xml_file_name = TiTs.createXmlFileOneIsotope(scan_dict)
        scan_dict['pipeInternals']['activeXmlFilePath'] = xml_file_name
        self.sql_stream.write_run_to_db(unix_time, xml_file_name)

        logging.info('preparing isotope: ' + scan_dict['isotopeData']['isotope'] +
                     ' of type: ' + scan_dict['isotopeData']['type'])
        # self.pipeline = Tpipe.find_pipe_by_seq_type(scan_dict, callback_sig)
        return self.prep_seq(scan_dict['isotopeData']['type'])  # should be the same sequencer for the whole isotope

    def init_analysis_thread(self, scan_dict, callback_sig=None,
                             live_plot_callback_tuples=None, fit_res_dict_callback=None,
                             scan_complete_callback=None):
        """ initialise the analysis thread in the first track """
        software_trig = False
        for key, track_dict in scan_dict.items():
            # go through all tracks and see if any steps are software triggered in feedback of dmm.
            if 'track' in key:
                software_trig = software_trig or track_dict['measureVoltPars']['duringScan'].get(
                    'measurementCompleteDestination', '') == 'software'
        if software_trig:
            # send the callback signal to the pipeline in order to enable software feedback when voltage is set
            # hardware triggering of the dmm is still possible
            dac_new_volt_set_callback = self.dac_new_volt_set_callback
        else:  # so the dmms are not software triggered.
            dac_new_volt_set_callback = None
        self.analysis_thread = AnalThr(
            scan_dict, callback_sig, live_plot_callback_tuples, fit_res_dict_callback,
            self.stop_analysis_sig, self.prep_track_in_pipe_sig, self.data_to_pipe_sig,
            scan_complete_callback, dac_new_volt_set_callback, self.scan_dev_step_request_callback
        )

    def get_existing_callbacks_from_main(self):
        """ check wether existing callbacks are still around in the main and then connect to those. """
        if Cfg._main_instance is not None:
            logging.info('ScanMain is connecting to existing callbacks in main')
            callbacks = Cfg._main_instance.gui_live_plot_subscribe()
            self.pre_post_meas_data_dict_callback = callbacks[6]

    def prepare_pre_scan_measurement(self, scan_dict, act_track_name, pre_post_scan_str):
        """
        call this function to PREPARE any device required for the pre-/during-/post- scan measurement
        :param scan_dict: dict, with all scan pars for the current iso, see Service/Scan/draftScanParameters.py:122
        :param act_track_name: str, name of the active track -> 'track0'
        :param pre_post_scan_str: str, either 'preScan' / 'duringScan' / 'postScan'
        :return: None
        """
        if pre_post_scan_str == 'preScan':
            self.select_scan_dev(scan_dict, act_track_name)
            self.prepare_scan_dev_for_scan(scan_dict, act_track_name)

        if pre_post_scan_str == 'preScan' or pre_post_scan_str == 'postScan':
            # do this for both!
            self.set_scan_dev_to_pre_scan(scan_dict, act_track_name, pre_post_scan_str)

        dmm_conf_dict = scan_dict[act_track_name]['measureVoltPars'].get(pre_post_scan_str, {}).get('dmms', {})
        self.prepare_dmms_for_scan(dmm_conf_dict)

        triton_dict = scan_dict[act_track_name].get('triton', {})
        self.prepare_triton_listener_for_scan(triton_dict, pre_post_scan_str, act_track_name)

        sql_dict = scan_dict[act_track_name].get('sql', {})
        self.prepare_sql_stream_for_scan(sql_dict, pre_post_scan_str, act_track_name)

        time.sleep(0.5)  # allow the device to settle for 500 ms

    def start_pre_scan_measurement(self, scan_dict, act_track_name, pre_post_scan_meas_str='preScan'):
        """
        Start the prescan Measurement of the Offset Voltage etc.
        using one or more digital Multimeters, Triton devices or an SQL stream.
            -> 0 V are applied from the DAC and the corrsponding post acceleration device (Fluke Heinzinger)
            is connected to the beamline
        :param scan_dict: dictionary, containing all scanparameters
        :param act_track_name: str, name of the active track -> 'track0'
        :param pre_post_scan_meas_str: str, either 'preScan' / 'duringScan' / 'postScan'
        :return: bool, True if success
        """
        # get the existing liveplotting callback from the main
        self.get_existing_callbacks_from_main()

        dmms_dict_pre_scan = scan_dict[act_track_name]['measureVoltPars'] \
            .get(pre_post_scan_meas_str, {}).get('dmms', None)
        dmms_dict_is_none = dmms_dict_pre_scan is None or dmms_dict_pre_scan == {}
        triton_dict_pre_scan = scan_dict[act_track_name].get('triton', {}).get(pre_post_scan_meas_str, {})
        triton_dict_is_none = triton_dict_pre_scan is None or triton_dict_pre_scan == {}
        sql_dict_pre_scan = scan_dict[act_track_name].get('sql', {}).get(pre_post_scan_meas_str, {})
        sql_dict_is_none = sql_dict_pre_scan is None or sql_dict_pre_scan == {}
        if dmms_dict_is_none and triton_dict_is_none and sql_dict_is_none:
            # return false if no measurement is wanted due to no existing dicts in dmms / triton / SQL.
            return False
        else:
            # TODO: Does this even have any effect? -> I commented it out for now (PM).
            # if 'continuedAcquisitonOnFile' not in scan_dict['isotopeData']:  # -> ergo
            #     # also delete any prescan reading there might be. for an ergo, keep them for a go
            #     for dmm_name, pre_scan_dict in dmms_dict_pre_scan.items():
            #         # print('prescandict is: ', pre_scan_dict)
            #         pre_scan_dict['readings'] = []
            #         # print('set readings of %s to []' % dmm_name)
            #     # also for triton:
            #     for dev, dev_ch_dict in triton_dict_pre_scan.items():
            #         for ch_name, ch_dict in dev_ch_dict.items():
            #             ch_dict['data'] = []
            #     # and SQL
            #     for ch_name, ch_dict in sql_dict_pre_scan.items():
            #         ch_dict['data'] = []
            track_num = int(act_track_name[5:])
            self.fpga_start_offset_measurement(scan_dict, track_num,
                                               pre_post_scan_meas_str)  # will be the first track in list.
            if not dmms_dict_is_none:
                self.digital_multi_meter.software_trigger_dmm('all')  # send a software trigger to all dmms
            if not triton_dict_is_none:
                self.start_triton_log()
            if not sql_dict_is_none:
                self.start_sql_log()
            self.dmm_pre_scan_done = dmms_dict_is_none
            self.triton_pre_scan_done = triton_dict_is_none
            self.sql_pre_scan_done = sql_dict_is_none
            return True

    def prescan_measurement(self, scan_dict, dmm_reading, pre_during_post_scan_str, tr_name, force_save_continue=False):
        """
        here all pre scan measurements are performed.
        :param scan_dict: dict, the usual scan dict
        :param dmm_reading: None or dict, dict will always contain at least one reading of one dmm
        :return: bool, True if finished.
        """
        if not self.dmm_pre_scan_done:  # when complete, do not check again (otherwise it saves again.)
            self.dmm_pre_scan_done = self.pre_scan_voltage_measurement(scan_dict, dmm_reading, pre_during_post_scan_str,
                                                                       tr_name, force_save_continue=force_save_continue)
        if not self.triton_pre_scan_done:  # when complete, do not check again (otherwise it saves again.)
            self.triton_pre_scan_done = self.check_triton_log_complete(scan_dict, pre_during_post_scan_str,
                                                                       tr_name, force_save_continue=force_save_continue)
        if not self.sql_pre_scan_done:  # when complete, do not check again (otherwise it saves again.)
            self.sql_pre_scan_done = self.check_sql_log_complete(scan_dict, pre_during_post_scan_str,
                                                                 tr_name, force_save_continue=force_save_continue)
        if self.dmm_pre_scan_done and self.triton_pre_scan_done and self.sql_pre_scan_done:
            return True
        else:
            return False

    def pre_scan_voltage_measurement(self, scan_dict, dmm_reading, pre_during_post_scan_str,
                                     tr_name, force_save_continue=False):
        """
        prescan voltage measurement, return True if all dmms have a value.
        Then save all values to file.
        Then setup dmms for during scan settings
        :param scan_dict:
        :param dmm_reading:
        :return: bool, True when finished
        """
        # print('reading of dmms prescan: ', dmm_reading)
        dmms_complete_check_sum = -1
        dmms_dict_pre_scan = scan_dict[tr_name]['measureVoltPars'].get(pre_during_post_scan_str, {}).get('dmms', None)

        if dmm_reading is not None:
            for dmm_name, volt_read in dmm_reading.items():
                if dmm_name in dmms_dict_pre_scan.keys():
                    # if the readback from this dmm is not wanted by the scan dict, just ignore it.
                    if volt_read is not None:
                        samples = dmms_dict_pre_scan[dmm_name]['sampleCount']
                        acquired_samples = dmms_dict_pre_scan[dmm_name]['acquiredPreScan']
                        still_to_acquire = max(0, samples - acquired_samples)
                        if len(volt_read) > still_to_acquire:  # too much data, need to shrink this
                            volt_read = volt_read[0:still_to_acquire]
                        dmms_dict_pre_scan[dmm_name]['readings'] += list(volt_read)
                        dmms_dict_pre_scan[dmm_name]['acquiredPreScan'] += len(volt_read)
                        # emit dmm_reading for live data plotting
                        logging.debug('emitting %s, from %s, value is %s'
                                      % ('pre_post_meas_data_dict_callback',
                                         'Service.Scan.ScanMain.ScanMain#pre_scan_voltage_measurement',
                                         str(scan_dict)))
                        self.pre_post_meas_data_dict_callback.emit(scan_dict)
            dmms_complete_check_sum = 0
            for dmm_name, dmm_dict in dmms_dict_pre_scan.items():
                samples = dmms_dict_pre_scan[dmm_name]['sampleCount']
                acquired_samples = dmms_dict_pre_scan[dmm_name]['acquiredPreScan']
                still_to_acquire = max(0, samples - acquired_samples)
                dmms_complete_check_sum += still_to_acquire

        if dmms_complete_check_sum == 0 or force_save_continue:  # done with reading when all dmms have a value
            logging.info('all dmms have a reading or forced to save')
            for dmm_name, dmm_dict in dmms_dict_pre_scan.items():
                dmms_dict_pre_scan[dmm_name]['acquiredPreScan'] = len(dmms_dict_pre_scan[dmm_name]['readings'])
                # print(dmm_name, dmms_dict_pre_scan[dmm_name]['acquiredPreScan'],
                #       dmms_dict_pre_scan[dmm_name]['readings'])
            self.abort_dmm_measurement('all')
            self.save_dmm_readings_to_file(scan_dict, tr_name, pre_during_post_scan_str)
            return True
        else:  # not complete and not forced
            return False

    ''' scan device related '''
    # a scan device is the device which is scanned during the acquisition,
    #  can be something like a DAC or a Laser, etc.
    def select_scan_dev(self, scan_dict, act_track_name):
        """
        Load the control module for the selected scan device according to the
        scanDevice dict in the current track.
        :param scan_dict: dict, with all scan pars for the current iso, see Service/Scan/draftScanParameters.py:122
        :param act_track_name: str, name of the active track -> 'track0'
        :return: None
        """
        scan_dev_dict = scan_dict[act_track_name].get('scanDevice', {})
        if scan_dev_dict != {}:
            dev_class = scan_dev_dict.get('devClass', None)
            sc_dev_n = scan_dev_dict.get('name', None)
            dev_type = scan_dev_dict.get('type', None)
            self.select_scan_dev_by_class(dev_class, dev_type, sc_dev_n)

            # connect the pyqtsignal for a successful setting of a step
            # with self.scan_dev_tells_next_step_is_set(...)
            self.scan_dev.scan_dev_has_set_a_new_step_pyqtsig.connect(self.scan_dev_tells_next_step_is_set)

    def select_scan_dev_by_class(self, sc_dev_class, dev_type=None, sc_dev_n=None):
        """
        select the scan device by the given class
        :param sc_dev_class: str, class name of the given device
        :param dev_type: str, dev type of the given device
        :param sc_dev_n: str, dev name of the given device,
            for Triton devices: leave None if you do not want to subscribe now.
        :return:
        """
        if sc_dev_class is not None:
            if dev_type == NiUsb6225ScanDevice.DEV_TYPE:
                # Local NI USB-6225 backend (UI may group it under DAC, FPGA still handled separately).
                self.scan_dev = NiUsb6225ScanDevice(sc_dev_n)
            elif sc_dev_class == 'Triton':
                self.scan_dev = self.triton_scan_controller
                if sc_dev_n is not None:  # Tilda specific
                    self.scan_dev.subscribe_to_scan_dev(sc_dev_n)
            elif sc_dev_class == 'DAC':
                self.scan_dev = AD57X1ScanDev()

    def prepare_scan_dev_for_scan(self, scan_dict, act_track_name):
        """
        prepare the previously selected scan device for the scan
        :param scan_dict: dict, with all scan pars for the current iso, see Service/Scan/draftScanParameters.py:122
        :param act_track_name: str, name of the active track -> 'track0'
        :return: None
        """
        scan_dev_dict = scan_dict[act_track_name].get('scanDevice', {})
        if scan_dev_dict != {}:
            start = scan_dev_dict.get('start', None)
            stepsize = scan_dev_dict.get('stepSize', None)
            num_of_steps = scan_dict[act_track_name].get('nOfSteps', None)
            num_of_scans = scan_dict[act_track_name].get('nOfScans', None)
            invert_in_odd_scans = scan_dict[act_track_name].get('invertScan', None)
            self.scan_dev.setup_scan_in_scan_dev(start, stepsize, num_of_steps, num_of_scans, invert_in_odd_scans)

    def set_scan_dev_to_pre_scan(self, scan_dict, act_track_name, pre_post_scan_str):
        """
        set the scan dev which is selected in the scan dict for this track to the desired value
        :param scan_dict: dict, with all scan pars for the current iso, see Service/Scan/draftScanParameters.py:122
        :param act_track_name: str, name of the active track -> 'track0'
        :param pre_post_scan_str: str, either 'preScan' / 'duringScan' / 'postScan'
        :return: None
        """
        scan_dev_dict = scan_dict[act_track_name].get('scanDevice', {})
        if scan_dev_dict != {}:
            set_point_key = 'preScanSetPoint' if pre_post_scan_str == 'preScan' else 'postScanSetPoint'
            set_val = scan_dev_dict.get(set_point_key, None)
            if set_val is not None:  # will be None for DuringScan
                self.scan_dev.set_pre_scan_masurement_setpoint(set_val)
        else:
            logging.warning('warning, could not find scanDevice dict in'
                            ' the track pars of %s will not set scan device to anything.' % act_track_name)

    def request_next_step_sc_dev_from_sc_main(self, step_num):
        """
        request the scan dev to set the next step.
        This is triggered from the pipeline, when a next step request is sent from the fpga!
        The scan device will tell the scan_main when it is done via a pyqtsignal -> scan_dev_has_set_a_new_step_pyqtsig
        """
        # set glob var in fpga to False to arm for next step
        # this must be done BEFORE requesting the step, because the FPGA is now waiting for a rising edge.
        self.sequencer.scanDeviceReadyForStep(False)
        # request preparation of next step from scan device and pass callback
        # req_time = datetime.now()  # TODO: implement a timeout here? Or a warning for the user when waiting too long?
        self.scan_dev.request_next_step()
        logging.debug('%s: requested next step from scan device now. Step number is %s' % ('scan_main', step_num))

    def scan_dev_tells_next_step_is_set(self, scan_progress_dict):
        """
        connected to self.scan_dev.scan_dev_has_set_a_new_step_pyqtsig,
        which will be emitted when the scan device has set a new step.
        :param scan_progress_dict: dict,
            {'curStep': self.sc_l_cur_step,
            'curScan': self.sc_l_cur_scan,
            'percentOfScan': self.sc_l_perc_compl,
            'curStepVal': self.sc_one_scan_vals[self.sc_l_cur_step],
            'scanStatus': self.scan_status}
        """
        # trigger next step on fpga -> really communicate with fpga here!
        set_time = datetime.now()
        self.sequencer.scanDeviceReadyForStep(True)
        logging.debug('{}: received step ready signal from scan device. Passed on to sequencer.'.format(set_time))

    ''' post acceleration related functions: '''

    def init_post_accel_pwr_supplies(self):
        """
        restarts and connects to the power devices
        """
        return self.post_acc_main.power_supply_init()

    def deinit_post_accel_pwr_supplies(self):
        """
        deinitialize all active power supplies
        """
        self.post_acc_main.power_supply_deinit()

    def set_post_accel_pwr_supply(self, power_supply, volt):
        """
        function to set the desired Heinzinger to the Voltage that is needed.
        """
        readback = self.post_acc_main.set_voltage(power_supply, volt)
        return readback

    def set_post_accel_pwr_spply_output(self, power_supply, outp_bool):
        """
        will set the output according to outp_bool
        """
        self.post_acc_main.set_output(power_supply, outp_bool)

    def get_status_of_pwr_supply(self, power_supply, read_from_dev=True):
        """
        returns a list of dicts containing the status of the power supply,
        keys are: name, programmedVoltage, voltageSetTime, readBackVolt, output
        power_supply == 'all' will return status of all active power supplies
        if read_from_dev is False: only return the last stored status.
        """
        if read_from_dev:
            ret = self.post_acc_main.status_of_power_supply(power_supply)
        else:
            ret = self.post_acc_main.power_sup_status
        return ret

    ''' sequencer / fpga related functions: '''

    def prep_seq(self, seq_type):
        """
        prepare the sequencer before scanning -> load the correct bitfile to the fpga.
        """
        if self.sequencer is None:  # no sequencer loaded yet, must load
            logging.debug('loading sequencer of type: ' + seq_type)
            self.sequencer = FindSeq.ret_seq_instance_of_type(seq_type)
        else:
            if seq_type == 'kepco':
                if 'dummy' in self.sequencer.type or self.sequencer.type not in DftScan.sequencer_types_list:
                    logging.debug('loading cs in order to perform kepco scan')
                    self.deinit_fpga()
                    self.sequencer = FindSeq.ret_seq_instance_of_type('cs')
            elif self.sequencer.type != seq_type:  # check if current sequencer type is already the right one
                logging.debug('loading sequencer of type: ' + seq_type)
                self.deinit_fpga()
                self.sequencer = FindSeq.ret_seq_instance_of_type(seq_type)
        if self.sequencer is None:  # if no matching sequencer is found (e.g. missing hardware) return False
            logging.warning('sequencer could not be started')
            return False
        else:
            logging.info('sequencer successfully started')
            return True

    def deinit_fpga(self, finalize_com=False):
        """
        deinitilaizes the fpga
        """
        if self.sequencer is not None:
            self.sequencer.DeInitFpga(finalize_com)
            self.sequencer = None

    def start_measurement(self, scan_dict, track_num):
        """
        will start the measurement for one track.
        After starting the measurement, the FPGA runs on its own.
        """
        act_track_name = 'track' + str(track_num)

        track_dict = scan_dict.get(act_track_name)
        iso = scan_dict.get('isotopeData', {}).get('isotope')
        logging.debug('---------------------------------------------')
        logging.debug('starting measurement of %s track %s  with track_dict: %s' %
                      (iso, track_num, str(track_dict)))
        logging.debug('---------------------------------------------')
        # logging.debug('postACCVoltControl is: ' + str(track_dict['postAccOffsetVoltControl']))  # this is fine.
        self.ppg_stop(False)  # stop the ppg, to ensure the daq is not triggered unintended
        start_ok = self.sequencer.measureTrack(scan_dict, track_num)
        self.ppg_load_track(track_dict)  # first start the measurement, then load the pulse pattern on th ppg
        self.ground_pin_warned = False

        # start triton log for during scan if required
        triton_dict_pre_scan = scan_dict[act_track_name].get('triton', {}).get('duringScan', {})
        triton_dict_is_none = triton_dict_pre_scan is None or triton_dict_pre_scan == {}
        sql_dict_pre_scan = scan_dict[act_track_name].get('sql', {}).get('duringScan', {})
        sql_dict_is_none = sql_dict_pre_scan is None or sql_dict_pre_scan == {}
        if not triton_dict_is_none:
            self.start_triton_log()
        if not sql_dict_is_none:
            self.start_sql_log()
        return start_ok

    def set_post_acc_switch_box(self, scan_dict, track_num, desired_state=None):
        """
        set the post acceleration switchbox to the desired state.
        teh state is defined in the trackdict['postAccOffsetVoltControl']
        the track dict is extracted from the scandict
        :param scan_dict: dict, containgn all scna pars
        :param track_num: int, number of the track
        """
        if desired_state is None:
            track_dict = scan_dict.get('track' + str(track_num))
            desired_state = track_dict['postAccOffsetVoltControl']
        self.switch_box_state_before_switch = self.sequencer.setPostAccelerationControlState(desired_state, False)
        self.switch_box_is_switched_time = None
        return deepcopy(desired_state)

    def post_acc_switch_box_is_set(self, des_state, switch_box_settle_time_s=5.0):
        """
        call this to check if the state of the hsb is already the desired one.
        :param des_state: int, the desired state of the box
        :return: tuple, (bool_True_if_success, int_current_state, int_desired_state)
        """
        try:
            if des_state == 4:  # will go to loading, no wait afterwards needed.
                switch_box_settle_time_s = 0.0
            done, currentState, desired_state = self.sequencer.getPostAccelerationControlStateIsDone(des_state)
            if done:
                if currentState == self.switch_box_state_before_switch:
                    #  the switchbox was already in the right state before switching,
                    #  so no additional wait is needed.
                    return done, currentState, desired_state
                else:
                    if self.switch_box_is_switched_time is None:
                        self.switch_box_is_switched_time = datetime.now()
                    now = datetime.now()
                    wait = now - self.switch_box_is_switched_time
                    done = wait >= timedelta(seconds=switch_box_settle_time_s)
                    if done:
                        self.switch_box_is_switched_time = None
            return done, currentState, desired_state
        except Exception as e:
            logging.error('error while setting hsb: %s' % e, exc_info=True)
            return False, 5, 5

    def fpga_start_offset_measurement(self, scan_dict, track_num, pre_post_scan_meas_str):
        """
        set all scanparameters at the fpga and go into the measure Offset state.
         set DAC to 0V
        dmms are triggered by software and voltmeter-complete TTL-from dmm is ignored.
        :return:bool, True if successfully changed State
        """
        self.sequencer.measureOffset(scan_dict, track_num, pre_post_scan_meas_str)

    def read_data(self, force_emit=False):
        """
        read the data coming from the fpga.
        The data will be directly fed to the pipeline.
        :param force_emit: bool,
            use False to emit data only every allowed interval, in order not to emit pyqtsignals every 50ms
            use True in order to force the emit of all newly incoming data and the data from storage!
                -> needed when stopping the scan
        :return: bool, True if nOfEle > 0 that were read
        """
        # and then send bigger packages at once.
        result = self.sequencer.getData()
        if result.get('nOfEle', -1) > 0 or self.incoming_raw_data_storage.size:
            # some new data came in or there is still data in the storage
            if result.get('nOfEle', -1) > 0 and result.get('newData', None) is not None:
                # logging.debug('appending: %s' % str(deepcopy(result['newData'])))
                # just emit it directly again
                self.data_to_pipe_sig.emit(deepcopy(result.get('newData', None)), {})
            return True
        else:
            return False

    def read_sequencer_status(self):
        if self.sequencer is not None:
            state = self.sequencer.getSeqState()
            for n_state, int_state in self.sequencer.config.seqStateDict.items():
                if int_state == state:
                    state = n_state
            timeout = 'fine'
            if self.sequencer.getDACQuWriteTimeout():
                timeout = 'timedout'
            # logging.debug('sequencer state is: %s' % state)
            return {'type': self.sequencer.type, 'state': state, 'DMA Queue status': timeout}
        else:
            return None

    def read_fpga_status(self):
        if self.sequencer is not None:
            session = self.sequencer.session.value
            status = self.sequencer.status
            state_num, state_str = self.sequencer.read_outbits_state()
            outb_arr = self.sequencer.read_outbits_number_of_cmds()
            return {'session': session, 'status': status,
                    'outbit state': (state_num, state_str), 'outbit_n_of_cmd': str(outb_arr)}
        else:
            return None

    def check_scanning(self):
        """
        check if the sequencer is still in the 'measureTrack' state
        :return: bool, True if still scanning
        """
        meas_state = self.sequencer.config.seqStateDict['measureTrack']
        seq_state = self.sequencer.getSeqState()
        return meas_state == seq_state

    def stop_measurement(self, complete_stop=False, clear=True):
        """
        stops all modules which are relevant for scanning.
        pipeline etc.
        """
        read = self.read_data(force_emit=True)  # read data one last time
        self.abort_triton_log()
        self.abort_sql_log()
        self.ppg_stop()
        status = 'aborted' if Cfg._main_instance.abort_scan else 'completed'
        self.sql_stream.conclude_run_in_db(time.mktime(datetime.today().timetuple()), status)
        if read:
            logging.info('while stopping measurement, some data was still read.')
        if complete_stop:  # only touch dmms in the end of the whole scan
            self.read_multimeter('all', True)
            self.abort_dmm_measurement('all')

        logging.info('stopping measurement, clear is: ' + str(clear))
        logging.debug('emitting %s, from %s, value is %s'
                      % ('stop_analysis_sig',
                         'Service.Scan.ScanMain.ScanMain#stop_measurement',
                         str((clear, complete_stop))))
        self.stop_analysis_sig.emit(clear, complete_stop)
        if complete_stop:  # only touch dmms in the end of the whole scan
            self.set_dmm_to_periodic_reading('all')

    def halt_scan(self, b_val):
        """
        halts the scan after the currently running track is completed
        """
        self.sequencer.halt(b_val)

    def abort_scan(self):
        """
        aborts the scan directly, will block until scan is aborted on the fpga.
        will also abort the scan on the scan device
        """
        self.sequencer.abort()
        self.scan_dev.abort_scan()

    def pause_scan(self, pause_bool=None):
        """
        This will pause the scan with a loop in the handshake.
        Use this, if the laser jumped or so and you want to continue on the data.
        :param pause_bool: bool, None if you want to toggle
        """
        self.sequencer.pause_scan(pause_bool)
        return self.sequencer.pause_bool

    def set_stop_volt_meas_bool(self, stop_bool):
        """
        set the stopVoltMeas Boolean on the fpga.
        If This is True, it will hold the fpga after the voltage is set.
        Setting it to False then will result the fpga to send out the usual hardware meas volt trigger
        and then it will wait for a hardware voltmeter complete feedback(or timeout),
        this wait can be stopped by setting the stopVoltMeas Boolean to True
        and should be done when all dmms have a reading for this voltage step.
        :param stop_bool: bool,
        :return: None
        """
        if self.sequencer is not None:
            logging.debug('setting stopVoltMeas to: %s' % stop_bool)
            self.sequencer.set_stopVoltMeas(stop_bool)
            return True
        else:
            logging.error('error: trying to access sequencer, but there is no sequencer initialised.'
                          ' Function call is: set_stop_volt_meas_bool() in scan main')
            return False

    def rcvd_dac_new_voltage_during_kepco_scan(self, dac_20Bitint):
        """
        Called when a new voltage is sent from the analysis pipeline.
        -> voltage on the FPGA is set and the software things
            (e.g. trigger all dmms by software for voltage measurement)
            for this step can be done.
        :param dac_20Bitint: int, dac 20 bit integer indicating which dac step was lastly analyzed in the pipeline.
        :return:
        """
        if dac_20Bitint >= 0:  # it means dac voltage is set
            logging.debug('received a new voltage step dac int is: %s' % dac_20Bitint)
            self.software_trigger_dmm('all')
            self.set_stop_volt_meas_bool(False)
        else:  # this means all dmms returned a reading and proceed to next step please
            self.kepco_scan_all_dmms_have_reading()

    def kepco_scan_all_dmms_have_reading(self):
        """
        will be activated from pipe when all dmms have a reading.
        """
        self.set_stop_volt_meas_bool(True)

    ''' Pipeline / Analysis related functions: '''

    def prep_track_in_pipe(self, track_num, track_index):
        """
        prepare the pipeline for the next track
        reset 'nOfCompletedSteps' to 0.
        """
        self.analysis_thread.start()
        logging.debug('emitting %s, from %s, value is %s'
                      % ('prep_track_in_pipe_sig',
                         'Service.Scan.ScanMain.ScanMain#prep_track_in_pipe',
                         str((track_num, track_index))))
        self.prep_track_in_pipe_sig.emit(track_num, track_index)

    def calc_scan_progress(self, progress_dict, scan_dict, start_time):
        """
        calculates the scan progress by comparing the given dictionaries.
        progress_dict must contain: {activeIso: str, activeTrackNum: int, completedTracks: list, nOfCompletedSteps: int}
        scan_dict_contains scan values only for active scan
        return_dict contains: ['activeIso', 'overallProgr', 'timeleft', 'activeTrack', 'totalTracks',
        'trackProgr', 'activeScan', 'totalScans', 'activeStep','actStepIndex' 'totalSteps', 'trackName']
        """
        try:
            return_dict = dict.fromkeys(['activeIso', 'overallProgr', 'timeleft', 'activeTrack', 'totalTracks',
                                         'trackProgr', 'activeScan', 'totalScans', 'activeStep',
                                         'totalSteps', 'trackName', 'activeFile'])
            iso_name = progress_dict['activeIso']
            track_num = progress_dict['activeTrackNum']
            track_name = 'track' + str(track_num)
            compl_tracks = progress_dict['completedTracks']
            compl_steps = progress_dict['nOfCompletedSteps']
            n_of_tracks, list_of_track_nums = TiTs.get_number_of_tracks_in_scan_dict(scan_dict)
            track_ind = list_of_track_nums.index(track_num)
            total_steps_list, total_steps = SdOp.get_num_of_steps_in_scan(scan_dict)
            if n_of_tracks > 1:
                steps_this_act_tr = scan_dict[track_name]['nOfSteps'] * scan_dict[track_name]['nOfScans']
                if steps_this_act_tr == compl_steps:
                    # the active track is just complete,
                    #  so dont account those steps, they are already accounted in compl_steps!
                    if track_num in compl_tracks:
                        compl_tracks = deepcopy(compl_tracks)
                        compl_tracks.remove(track_num)
                steps_in_compl_tracks = sum(total_steps_list[ind][2] for ind, track_n in enumerate(compl_tracks))
            else:
                # only one track and therefore all completed steps are accounted in progress_dict['completedTracks']
                steps_in_compl_tracks = 0
            return_dict['activeIso'] = iso_name
            return_dict['overallProgr'] = float(steps_in_compl_tracks + compl_steps) / total_steps * 100
            # timeleft droht gefahr durch 0 zu teilen
            return_dict['timeleft'] = str(self.calc_timeleft(start_time, (steps_in_compl_tracks + compl_steps),
                                                             (total_steps - (steps_in_compl_tracks + compl_steps)))
                                          ).split('.')[0]
            return_dict['activeTrack'] = track_ind + 1
            return_dict['totalTracks'] = len(list_of_track_nums)
            return_dict['trackProgr'] = float(compl_steps) / total_steps_list[track_ind][2] * 100
            return_dict['activeScan'] = int(compl_steps / total_steps_list[track_ind][1]) + \
                                        (compl_steps % total_steps_list[track_ind][1] > 0)
            return_dict['totalScans'] = total_steps_list[track_ind][0]
            return_dict['activeStep'] = compl_steps - (return_dict['activeScan'] - 1) * total_steps_list[track_ind][1]
            return_dict['totalSteps'] = total_steps_list[track_ind][1]
            if return_dict['activeScan'] % 2 == 0 and scan_dict[track_name]['invertScan']:
                return_dict['actStepIndex'] = return_dict['totalSteps']-return_dict['activeStep']
            else:
                return_dict['actStepIndex'] = return_dict['activeStep']-1
            return_dict['trackName'] = track_name
            return_dict['activeFile'] = scan_dict['pipeInternals']['activeXmlFilePath']
            dif = datetime.now() - self.last_scan_prog_update
            if dif > timedelta(seconds=5):
                self.last_scan_prog_update = datetime.now()
                logging.info('%s  ---  iso %s is still scanning, active track is: %s  '
                             'timeleft is: %s' % (datetime.now(), iso_name, track_name, return_dict['timeleft']))
            return return_dict
        except Exception as e:
            logging.error('while calculating the scan progress, this happened: ' + str(e), exc_info=True)
            return None

    def calc_timeleft(self, start_time, already_compl_steps, steps_still_to_complete):
        """
        calculate the time that is left until the whole scan is completed.
        Therfore measure the expired time since scan start and compare it with remaining steps.
        :return: timedelta, time that is left
        """
        now_time = datetime.now()
        dt = now_time - start_time
        if steps_still_to_complete and already_compl_steps:
            timeleft = max(dt / already_compl_steps * steps_still_to_complete, timedelta(seconds=0))
        else:
            timeleft = timedelta(seconds=0)
        return timeleft

    def analysis_done_check(self):
        """
        will return True if the Analysis is complete (-> Thread is not runnning anymore).
        Be sure to stop it before with self.stop_measurement
        """
        return not self.analysis_thread.isRunning()

    ''' Digital Multimeter Related '''

    def prepare_dmm(self, type_str, address):
        """
        will initialize a multimeter of given type and address.
        :param address: str, address of the Multimeter
        :param type_str: str, type of Multimeter
        :return: str, name of the initialized Multimeter
        """
        name = self.digital_multi_meter.find_dmm_by_type(type_str, address)
        return name

    def prepare_dmms_for_scan(self, dmms_conf_dict, dmm_meas_volt_complete_location=None):
        """
        call this pre scan in order to configure all dmms according to the
        dmms_conf_dict, which is located in scan_dict['trackName']['measureVoltPars']['preScan' or 'duringScan']['dmms].
        each dmm will be resetted before starting.
        set pre_scan_meas to True to ignore the contents of the current config dict and
         load from pre config
        """
        logging.debug('preparing dmms for scan. Config dict is: %s' % dmms_conf_dict)
        active_dmms = self.get_active_dmms()
        logging.debug('active dmms: %s' % list(active_dmms.keys()))
        self.dmm_feed_pipe = True if dmms_conf_dict or self.sequencer.type == 'kepco' else False
        for dmm_name, dmm_conf_dict in dmms_conf_dict.items():
            dmms_conf_dict[dmm_name]['acquiredPreScan'] = 0  # reset the acquired samples
            if dmm_name not in active_dmms:
                logging.warning('%s was not initialized yet, will do now.' % dmm_name)
                self.prepare_dmm(dmm_conf_dict.get('type', ''), dmm_conf_dict.get('address', ''))
            self.setup_dmm_and_arm(dmm_name, dmm_conf_dict, False)
        # if the stop bool is not addressed, set it to false pre scan in order not to hinder scanning procedure.
        stop_bool = dmm_meas_volt_complete_location == 'software' and dmm_meas_volt_complete_location is not None
        self.set_stop_volt_meas_bool(stop_bool)

    def setup_dmm_and_arm(self, dmm_name, config_dict, reset_dev):
        """
        function to load a configuration dictionary to a dmm and prepare this for a measurement.
        :param dmm_name: str, name of the dmm 'type_address'
        :param config_dict: dict, containing all necessary parameters for the given dmm
        :param reset_dev: bool, True for resetting
        """
        self.abort_dmm_measurement(dmm_name)
        self.read_multimeter(dmm_name, False)  # read remaining values from buffer.
        self.digital_multi_meter.config_dmm(dmm_name, config_dict, reset_dev)
        self.digital_multi_meter.start_measurement(dmm_name)
        time.sleep(1)

    def read_multimeter(self, dmm_name, feed_pipe):
        """
        reads all available values from the multimeter and returns them as an array.
        :return: dict, key is name of dmm
        or None if no reading
        """
        if dmm_name == 'all':
            ret = self.digital_multi_meter.read_from_all_active_multimeters()
        else:
            ret = self.digital_multi_meter.read_from_multimeter(dmm_name)
        worth_feeding = False
        if ret is not None and feed_pipe:  # will be None if no dmms are active
            for dmm_name, val in ret.items():
                if val is not None:
                    worth_feeding = True
            if self.analysis_thread is not None and worth_feeding and not self.sequencer.pause_bool:
                logging.debug('emitting %s, from %s, value is %s'
                              % ('data_to_pipe_sig',
                                 'Service.Scan.ScanMain.ScanMain#read_multimeter',
                                 str((np.zeros(0, dtype=np.int32), ret))))
                self.data_to_pipe_sig.emit(np.zeros(0, dtype=np.int32), ret)
                self.check_ground_pin_warn_user(ret)  # Add this to options if needed.

        return ret

    def check_ground_pin_warn_user(self, dmm_readback_dict, zero_range=0.05):
        """ function to open a window when a dmm returns an absolute value below zero_range """
        for key, val in dmm_readback_dict.items():
            if val is not None:
                if len(val[np.abs(val) < zero_range]) and not self.ground_pin_warned:
                    if self.ground_warning_win is not None:
                        self.ground_warning_win.close()
                    self.ground_pin_warned = True
                    self.ground_warning_win = QtWidgets.QMainWindow()
                    self.ground_warning_win.setWindowTitle('ground pin warning!')
                    palette = Qt.QPalette()
                    palette.setColor(Qt.QPalette.Background, Qt.QColor.fromRgb(255, 128, 0, 255))
                    centr_widg = QtWidgets.QWidget()
                    lay = QtWidgets.QVBoxLayout()
                    label = QtWidgets.QLabel('---- Warning! ----- ')
                    label.setAlignment(Qt.Qt.AlignCenter)
                    lay.addWidget(label)
                    lay.addWidget(QtWidgets.QLabel('dmm: %s yielded a measurement close to 0V\n'
                                                   ' is the setup grounded?' % key))
                    centr_widg.setLayout(lay)
                    self.ground_warning_win.setCentralWidget(centr_widg)
                    self.ground_warning_win.setPalette(palette)
                    self.ground_warning_win.show()

    def request_config_pars(self, dmm_name):
        """
        request the config_pars dict as a deepocpy.
        :param dmm_name: str, name of the device
        :return: dict, copy of the config pars.
        """
        return deepcopy(self.digital_multi_meter.get_raw_config_pars(dmm_name))

    def request_dmm_available_preconfigs(self, dmm_name):
        confs = self.digital_multi_meter.get_available_preconfigs(dmm_name)
        return confs

    def get_active_dmms(self):
        """
        function to return a dict of all active dmms
        :return: dict of tuples, {dmm_name: (type_str, address_str, state_str, last_readback, configPars_dict)}
        """
        return self.digital_multi_meter.get_active_dmms()

    def set_dmm_to_periodic_reading(self, dmm_name):
        """
        set the dmm to a predefined configuration in that it reads out a value every now and then.
        this will configure the dmm and afterwards initiate the measurement directly.
        :param dmm_name: str, type 'all' for all active dmms
        """
        self.digital_multi_meter.start_pre_configured_meas(dmm_name, 'periodic')

    def set_dmm_to_pre_config(self, dmm_name, preconfigname):
        self.digital_multi_meter.start_pre_configured_meas(dmm_name, preconfigname)

    def abort_dmm_measurement(self, dmm_name):
        """
        this will abort the running measurement on the given dmm.
        type 'all' to stop all running dmms
        :param dmm_name: str, name of dmm
        """
        self.digital_multi_meter.stopp_measurement(dmm_name)

    def software_trigger_dmm(self, dmm_name):
        self.digital_multi_meter.software_trigger_dmm(dmm_name)

    def de_init_dmm(self, dmm_name):
        """
        deinitialize the given multimeter and remove it from the self.digital_multi_meter.dmm dictionary
        :param dmm_name: str, name of the given device.
        """
        self.digital_multi_meter.de_init_dmm(dmm_name)

    def save_dmm_readings_to_file(self, scan_dict, tr_name, pre_during_post_scan_str='preScan'):
        """
        save the readings of the dmm directly to the
        :param scan_dict: dict as the suual scan dict.
        :param pre_during_post_scan_str: str, preScan / duringScan / postScan
        :return:
        """
        file = scan_dict['pipeInternals']['activeXmlFilePath']
        dmms_dict = scan_dict[tr_name]['measureVoltPars'].get(pre_during_post_scan_str, {}).get('dmms', {})
        # the save process is moved to TildaTools, so its better accessible
        TiTs.save_dmm_readings_to_xml(file, tr_name, dmms_dict, pre_during_post_scan_str)

    def dmm_get_accuracy(self, dmm_name, config):
        """ get the accuracy tuple from the dmm with the given config """
        return self.digital_multi_meter.get_accuracy(dmm_name, config)

    ''' Pulse Pattern Generator related '''

    def ppg_init(self):
        """ initialise the pulse pattern generator bitfile on the fpga """
        if self.pulse_pattern_gen is None:
            try:
                self.pulse_pattern_gen = PPG.PulsePatternGenerator()
            except Exception as e:
                logging.error('error: %s could not initialise PulsePatternGenerator,'
                              ' WILL START DUMMY NOW' % e, exc_info=True)
                self.pulse_pattern_gen = PPGDummy.PulsePatternGeneratorDummy()
        else:
            logging.error('error, could not initialize the fpga bitfile,'
                          ' because there is already a running ppg session: %s\n'
                          'deinitialise this and then try again.' % self.pulse_pattern_gen.session)

    def ppg_deinit(self, finalize_com=False):
        """ stop the bitfile on the control fpga """
        if self.pulse_pattern_gen is not None:
            self.pulse_pattern_gen.deinit_ppg(finalize_com)
            # self.pulse_pattern_gen.ppg_state_callback_disconnect()
            self.pulse_pattern_gen = None

    def ppg_load_track(self, track_dict):
        """ start the pulse pattern generator according to the cmd list in the track_dict['pulsePattern'] """
        ppg_dict = track_dict.get('pulsePattern', {})
        if ppg_dict:
            if self.pulse_pattern_gen is None:
                self.ppg_init()
            cmd_list = ppg_dict.get('cmdList', [])
            if cmd_list:
                self.ppg_run_with_list_of_commands(cmd_list)

    def ppg_run_with_list_of_commands(self, list_of_cmds):
        """ reset the ppg and load the list of cmds to it, then run it. """
        if self.pulse_pattern_gen is None:
            self.ppg_init()
        if len(list_of_cmds) > 30:
            logging.info('loading pulse pattern generator with list of commands: [%s, ... %s]'
                         % (str(list_of_cmds[0:10])[1:-1], str(list_of_cmds[-10:-1])[1:-1]))
        else:
            logging.info('loading pulse pattern generator with list of commands: %s' % list_of_cmds)
        self.pulse_pattern_gen.load(self.pulse_pattern_gen.convert_list_of_cmds(list_of_cmds),
                                    start_after_load=True, reset_before_load=True)

    def ppg_stop(self, reset=False):
        """
        stops the pulse pattern generator from executing, delete pattern from memory if wanted by reset=True
        Always include a $stop command in order to have a defined stopping state for the outputs.
        This will NOT remove the bitfile from the fpga.
        """
        if self.pulse_pattern_gen is not None:
            if reset:
                self.pulse_pattern_gen.reset()
            else:
                self.pulse_pattern_gen.stop()

    def ppg_state_callback_connect(self, callback_sig):
        """
        use this in order to connect a signal to the state changed function and
         emit the name of the satte each time this is changed.
        :param callback_sig: pyqtboundsignal(str)
        """
        if self.pulse_pattern_gen is None:
            self.ppg_init()
        self.pulse_pattern_gen.connect_to_state_changed_signal(callback_sig)

    def ppg_state_callback_disconnect(self):
        self.pulse_pattern_gen.disconnect_to_state_changed_signal()

    """ Triton related """

    def prepare_triton_listener_for_scan(self, triton_scan_dict, pre_post_scan_str='preScan', track_name='track0'):
        """
        setup the triton listener if this has not ben setup yet.
        subscribe to all channels as defined in the triton_scan_dict.
        :param triton_scan_dict: dict of dicts, e.g.:
        {'prescan': {'dev1': {'ch1': {'data': [], 'required': 2, 'acquired': 0},
                           'ch2': {'data': [], 'required': 5, 'acquired': 0}}},
        'postscan': {...}}
        :return: None
        """
        logging.debug('preparing TRITON Listener for %s measurement. Config dict is: %s'
                      % (pre_post_scan_str, triton_scan_dict.get(pre_post_scan_str, {})))
        if self.triton_listener is None:
            self.triton_listener = TritonListener(self.triton_listener_name)
        if self.triton_listener.logging:
            self.triton_listener.stop_log()
        self.triton_listener.setup_log(triton_scan_dict.get(pre_post_scan_str, {}), pre_post_scan_str, track_name)

    def stop_triton_listener(self, stop_dummy_dev=True, restart=False):
        """
        remove the triton listener and unsubscribe from devices.
        """
        if self.triton_listener is not None:
            self.triton_listener._stop()
            self.triton_listener = None
        if restart:
            self.triton_listener = TritonListener(self.triton_listener_name)

    def abort_triton_log(self):
        """ this just stops the log and leaves the listener alive """
        if self.triton_listener is not None:
            self.triton_listener.stop_log()

    def start_triton_log(self):
        """ must have been set up first """
        if self.triton_listener is not None:
            self.triton_listener.start_log()

    def check_triton_log_complete(self, scan_dict, pre_during_post_scan_str, tr_name, force_save_continue=False):
        """ check if the triton logger completed """
        if self.triton_listener is not None:
            if self.triton_listener.logging_complete or force_save_continue:
                self.save_triton_log(scan_dict, tr_name, pre_during_post_scan_str)
                if self.triton_listener.logging:
                    self.abort_triton_log()
                return True
            else:
                return False
        else:
            logging.warning('triton log not existing')
            return True

    def get_triton_log_data(self):
        """
        get the data in the triton log
        :return: dict, {'dummyDev': {'ch1': {'required': 2, 'data': [], 'acquired': 0}, ...}}
        """
        if self.triton_listener is not None:
            return self.triton_listener.log
        else:
            return {}

    def save_triton_log(self, scan_dict, tr_name, pre_during_post_scan_str='preScan'):
        """
        save the currently logged data to the file defined in the scan pars
        :param scan_dict: dict, the usual scan dict, see  Service/Scan/draftScanParameters.py
        """
        file = scan_dict['pipeInternals']['activeXmlFilePath']
        triton_dict = self.get_triton_log_data()
        # The save process is moved to TildaTools for better accessibility
        TiTs.save_triton_to_xml(file, tr_name, triton_dict, pre_during_post_scan_str=pre_during_post_scan_str)

    def get_available_triton(self):
        """
        return a dict with all channels and their channels as a list.
        If no db available, use the self created dummy device.
        :return: dict, {dev: ['ch1', 'ch2' ...]}
        """
        if self.triton_listener is not None:
            return self.triton_listener.get_devs_from_db()
        else:
            return {}

    def get_triton_receivers(self):
        """
        get a list of all subscribed devices
        :return: list, ['dev0', 'dev1', ... ]
        """
        if self.triton_listener is None:
            return []
        else:
            return self.triton_listener.get_receivers()

    """ SQLStream related """

    def prepare_sql_stream_for_scan(self, sql_scan_dict, pre_post_scan_str='preScan', track_name='track0'):
        """
        set up the sql stream if it has not been set up yet.

        :param sql_scan_dict: dict of dicts, e.g.:
        {'prescan': {'ch1': {'data': [], 'required': 2, 'acquired': 0},
                     'ch2': {'data': [], 'required': 5, 'acquired': 0}},
         'postscan': {...}}
        :param pre_post_scan_str: str, preScan / duringScan / postScan.
        :param track_name: str, Name of the track.
        :return: None
        """
        logging.debug('preparing sql stream for %s measurement. Config dict is: %s'
                      % (pre_post_scan_str, sql_scan_dict.get(pre_post_scan_str, {})))
        if self.sql_stream is None:
            self.sql_stream = db_logger() #SQLStream()
        if self.sql_stream.logging_enabled:
            self.sql_stream.stop_log()
        self.sql_stream.setup_log(sql_scan_dict.get(pre_post_scan_str, {}), pre_post_scan_str, track_name)

    def stop_sql_stream(self, restart=False):
        """
        remove the sql listener and unsubscribe from devices.
        """
        if self.sql_stream is not None:
            self.sql_stream.stop_log()
            self.sql_stream = None
        if restart:
            self.sql_stream = db_logger()  #SQLStream()

    def abort_sql_log(self):
        """ this just stops the log and leaves the sql stream alive """
        if self.sql_stream is not None:
            self.sql_stream.stop_log()

    def start_sql_log(self):
        """ must have been set up first """
        if self.sql_stream is not None:
            self.sql_stream.start_log()

    def check_sql_log_complete(self, scan_dict, pre_during_post_scan_str, tr_name, force_save_continue=False):
        """ check if the sql logger completed """
        if self.sql_stream is not None:
            if self.sql_stream.logging_complete or force_save_continue:
                self.save_sql_log(scan_dict, tr_name, pre_during_post_scan_str)
                if self.sql_stream.logging_enabled:
                    self.abort_sql_log()
                return True
            else:
                return False
        else:
            logging.warning('sql log not existing')
            return True

    def get_sql_log_data(self):
        """
        get the data in the sql log
        :return: dict, {'ch1': {'required': 2, 'data': [], 'acquired': 0}, ...}
        """
        if self.sql_stream is not None:
            return self.sql_stream.log
        else:
            return {}

    def save_sql_log(self, scan_dict, tr_name, pre_during_post_scan_str='preScan'):
        """
        save the currently logged data to the file defined in the scan pars
        :param scan_dict: dict, the usual scan dict, see  Service/Scan/draftScanParameters.py
        :param tr_name: Name of the track.
        :param pre_during_post_scan_str: str, preScan / duringScan / postScan.
        """
        file = scan_dict['pipeInternals']['activeXmlFilePath']
        sql_dict = self.get_sql_log_data()
        # The save process is moved to TildaTools for better accessibility
        TiTs.save_sql_to_xml(file, tr_name, sql_dict, pre_during_post_scan_str=pre_during_post_scan_str)

    def get_available_sql_channels(self):
        if self.sql_stream is not None:
            return self.sql_stream.get_channels_from_db()
        else:
            return {}

if __name__ == "__main__":
    scn_main = ScanMain()
#     dmm_name = scn_main.prepare_dmm('Ni4071', 'PXI1Slot5')
#     cfg_raw = scn_main.request_config_pars(dmm_name)
#     cfg = {key: val[-1] for key, val in cfg_raw.items()}
#     cfg['triggerSource'] = 'interval'
#     print(cfg)
#     scn_main.setup_dmm_and_arm(dmm_name, cfg, True)
#     i = 0
#     while i <= 1000:
#         i += 1
#         readback = scn_main.read_multimeter('all')
#         for dmm_name, vals in readback.items():
#                 if vals is not None:
#                     print(vals)
#         time.sleep(0.002)
#     scn_main.abort_dmm_measurement('all')
#     readback = scn_main.read_multimeter('all')
#     print(readback)

