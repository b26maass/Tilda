"""

Created on '09.07.2015'

@author:'simkaufm'

"""

import ctypes
import logging

import numpy as np

from datetime import datetime

import Tilda.Driver.DataAcquisitionFpga.ContinousSequencerConfig as CsCfg
import Tilda.Service.Formatting as Form
from Tilda.Driver.DataAcquisitionFpga.MeasureVolt import MeasureVolt
from Tilda.Driver.DataAcquisitionFpga.SequencerCommon import Sequencer


class ContinousSequencer(Sequencer, MeasureVolt):
    def __init__(self):
        """
        Dummy Continous Sequencer
        """
        self.config = CsCfg
        super(Sequencer, self).__init__(self.config.bitfilePath, self.config.bitfileSignature,
                                        self.config.fpgaResource, dummy=True)
        self.type = 'csdummy'
        self.artificial_build_data = []
        self.scan_dev = 'DAC'  # Can use dummy with an external scan dev
        self.scan_dev_timeout = 1  # in seconds. Relevant if using external scan dev
        self.scanDevSet = True  # relevant if using external scan dev
        self.isKepcoScan = False
        self.steps = 0  # number of steps requested for this track
        self.next_step_req_time = datetime.now()
        self.status = CsCfg.seqStateDict['init']
        self.session = ctypes.c_ulong(0)
        self.status = 0

    '''read Indicators'''

    def getDACQuWriteTimeout(self):
        """
        always False in dummy Mode
        :return: bool, True if timedout
        """
        return False

    def getSPCtrQuWriteTimeout(self):
        """
        always False in dummy Mode
        :return: bool, timeout indicator of the Simple Counter trying to write to the DMAQueue
        """
        return False

    def getSPerrorCount(self):
        """
        always 0 in dummy mode
        :return: int, the errorCount of the simpleCounter module on the fpga
        """
        return 0

    def getSPState(self):
        """
        always 0 in dummy mode
        :return:int, state of SimpleCounter Module
        """
        return 0

    def getInternalDACState(self):
        """
        True in dummy mode if scandev is DAC
        :return: bool: True if DAC available
        """
        if self.scan_dev == 'DAC':
            return True
        else:
            return False

    '''set Controls'''

    def setDwellTime(self, scanParsDict, track_num):
        """
        always True in dummy Mode
        """
        return True

    def setScanDeviceParameters(self, scanDevDict):
        """
        Writes the chosen scanDev type to the FPGA.
        :param scanDev: str: Currently supported devices are "DAC"(0) and "Triton"(1)
        :return:
        """
        # write scan device class as int to fpga
        device_class = scanDevDict.get('devClass', 'DAC')
        if scanDevDict.get('type', '') == 'NI_USB6225_AO':
            device_class = 'Triton'
        # device_class = getattr(ScTypes, device_class)  # For Dummy it is easier to keep this as String!
        self.scan_dev = device_class
        # write timeout in 10ns units to fpga
        timeout_s = scanDevDict.get('timeout_s', 1)  # default: 1sec = 100 000 000 * 10ns
        self.scan_dev_timeout = timeout_s
        logging.debug('CsDummy: scan_device has ben set to %s, timeout is %s' % (self.scan_dev, self.scan_dev_timeout))

        return True  # always true for dummy

    def scanDeviceReadyForStep(self, ready_bool):
        """
        Sets the "scanDevSet" bool on the FPGA. Should be used to signal when a scan device is ready for the next step.
        If implemented on the FPGA might also be used to halt the measurement when the scan device is not stable any more.
        :param ready_bool: bool: True if the scan device is ready for the next step.
        :return:
        """
        self.scanDevSet = ready_bool
        if self.isKepcoScan:
            complete_lis = []
            complete_lis.append(Form.add_header_to23_bit(0, 3, 0, 1))  # means dac voltage set
            self.artificial_build_data = complete_lis

    def setAllContSeqPars(self, scanpars, track_num):
        """
        Set all Scanparameters, needed for the continousSequencer
        :param scanpars: dict, containing all scanparameters
        :return: bool, if success
        always True in dummy Mode
        """
        track_name = 'track' + str(track_num)
        self.setScanDeviceParameters(scanpars[track_name]['scanDevice'])
        # At this point we could intercept whether this is a kepco scan or normal cs
        if scanpars['isotopeData']['type'] == 'kepco':
            logging.info('this is a kepco scan')
            self.isKepcoScan = True
        return True

    def setPostAccelerationControlState(self, desiredState, blocking=True):
        """
        will set the PostAccelerationControl State, so one can chose which PowerSupply will be used.
        :return: int, the current State of the Control Box
        """
        pass

    def getPostAccelerationControlStateIsDone(self, desired_state):
        """
        call this to check if the state of the hsb is already the desired one.
        :param desired_state: int, the desired state of the box
        :return: tuple, (bool_True_if_success, int_current_state, int_desired_state)
        """
        return True, desired_state, desired_state

    '''perform measurements:'''

    def measureOffset(self, scanpars, track_num, pre_post_scan_meas_str):
        """
        set all scanparameters at the fpga and go into the measure Offset state.
         set DAC to 0V
        :return:bool, True if successfully changed State
        """
        return True

    def measureTrack(self, scanpars, track_num):
        """
        set all scanparameters at the fpga and go into the measure Track state.
        Fpga will then measure one track independently from host and will finish either in
        'measComplete' or in 'error' state.
        In parallel, host has to read the data from the host sided buffer in parallel.
        :return:bool, True if successfully changed State
        """
        self.status = CsCfg.seqStateDict['measureTrack']
        logging.debug('measuring track: ' + str(track_num) +
                      '\nscanparameter are:' + str(scanpars))
        self.setAllContSeqPars(scanpars, track_num)
        if self.isKepcoScan:
            self.data_builder_kepco(scanpars)
        else:
            self.data_builder(scanpars, track_num)
        return True

    def data_builder(self, scanpars, track_num):
        """
        build data for one track and stroe it in self.artificial_build_data:
        Countervalue = Num_pmt + (num_of_step + 1)
        """
        track_ind, track_name = scanpars['pipeInternals'].get('activeTrackNumber', (0, 'track0'))
        trackd = scanpars[track_name]
        # x_axis = Form.create_x_axis_from_scand_dict(scanpars)[track_ind]  # not in dacRgeBit units anymore!
        num_of_steps = trackd['nOfSteps'] * trackd['nOfScans']
        # x_axis = [Form.add_header_to23_bit(x << 2, 3, 0, 1) for x in x_axis]
        complete_lis = []
        scans = 0
        while scans < trackd['nOfScans']:
            complete_lis.append(Form.add_header_to23_bit(2, 4, 0, 1))  # means scan started
            scans += 1
            j = 0
            while j < trackd['nOfSteps']:
                # simulate next step request
                if self.scan_dev != 'DAC':
                    complete_lis.append(Form.add_header_to23_bit(4, 4, 0, 1))  # means request next step
                # complete_lis.append(x_axis[j])  # TODO is it important that this is missing?
                # Yeah for nOfCompleted Steps
                j += 1
                i = 0
                while i < 8:
                    # append 8 pmt count events
                    complete_lis.append(Form.add_header_to23_bit(i + j, 2, i, 1))
                    i += 1
                    if i >= 8:
                        complete_lis.append(Form.add_header_to23_bit(1, int(b'0100', 2), 0, 1))  # step complete
        self.artificial_build_data = complete_lis

    def data_builder_kepco(self, scanpars=None):
        """
        In a dummy kepco scan we basically just need to emit next step signals and dac voltage set signals
        This data builder is only called once in the beginning and will therefore only emit the first step infos
        Everything else is handled by set_stopVoltMeas
        :param scanpars:
        :return:
        """
        complete_lis = []
        # first call, store some info from the scan pars!
        track_ind, track_name = scanpars['pipeInternals'].get('activeTrackNumber', (0, 'track0'))
        trackd = scanpars[track_name]
        self.steps = trackd['nOfSteps']  # remember how many steps we shall do
        complete_lis.append(Form.add_header_to23_bit(2, 4, 0, 1))  # means scan started
        # simulate next step request
        #if self.scan_dev != 'DAC':
        #    complete_lis.append(Form.add_header_to23_bit(4, 4, 0, 1))  # means request next step
        complete_lis.append(Form.add_header_to23_bit(0, 3, 0, 1))  # means dac voltage set
        self.artificial_build_data = complete_lis


    ''' overwriting interface functions here '''

    def getData_old(self):
        """
        nOfEle = int, number of Read Elements,
        newDataArray = numpy Array containing all data that was read
        elemRemainInFifo = int, number of Elements still in FifoBuffer
        :return:
        """
        result = {'nOfEle': 0, 'newData': None, 'elemRemainInFifo': 0}
        result['elemRemainInFifo'] = len(self.artificial_build_data)
        max_read_data = 10
        datapoints = 0
        if result['elemRemainInFifo'] > 0:
            datapoints = min(max_read_data, result['elemRemainInFifo'])
            result['newData'] = np.array(self.artificial_build_data[0:datapoints])
            result['nOfEle'] = datapoints
            result['elemRemainInFifo'] = len(self.artificial_build_data) - datapoints
        self.artificial_build_data = [i for j, i in enumerate(self.artificial_build_data)
                                      if j not in range(datapoints)]
        if result['elemRemainInFifo'] == 0:
            self.status = CsCfg.seqStateDict['measComplete']
        return result

    def getData(self):
        """
        Collect all data from artificial_build_data until a set next step request appears
        :return: artificially build data-dictionary
        """
        result = {'nOfEle': 0, 'newData': None, 'elemRemainInFifo': 0}
        result['elemRemainInFifo'] = len(self.artificial_build_data)
        if self.pause_bool:  # scan is paused, return no data
            return result
        else:
            max_read_data = 10
            datapoints = 0
            next_step_req_form = Form.add_header_to23_bit(4, 4, 0, 1)  # means request next step
            if self.scanDevSet:
                next_step_req_found = False
            else:
                # still waiting for next step, don't return new data yet
                next_step_req_found = True
            while not next_step_req_found and datapoints < max_read_data:
                if result['elemRemainInFifo'] > 0:
                    datapoints += 1
                    next_data = self.artificial_build_data.pop(0)  # directly take it from data stack, just to be sure
                    result['elemRemainInFifo'] = len(self.artificial_build_data)
                    if next_data == next_step_req_form:
                        self.scanDevSet = False
                        next_step_req_found = True
                        self.next_step_req_time = datetime.now()
                    # elif self.scan_dev is not 'DAC':
                    #     # check for timeout
                    #     time_since_last_step_request = datetime.now() - self.next_step_req_time
                    #     if time_since_last_step_request.seconds > self.scan_dev_timeout:
                    #         logging.warning('ContSeqDummy detected scanDevice timeout. Sending new data now anyways')
                    #         next_step_req_found = True
                    #         self.next_step_req_time = datetime.now()
                    new_datapoint = np.array(next_data)
                    if result['newData'] is None:
                        result['newData'] = new_datapoint
                    else:
                        result['newData'] = np.append(result['newData'], new_datapoint)
                    result['nOfEle'] = datapoints
                if result['elemRemainInFifo'] == 0:
                    if not self.isKepcoScan:
                        # if this is a kepco scan, more dummy data will be generated during the scan
                        self.status = CsCfg.seqStateDict['measComplete']
                    max_read_data = 0
            return result

    def getSeqState(self):
        return self.status

    def abort(self):
        self.steps = 0
        self.artificial_build_data = []
        return True

    def halt(self, val):
        logging.info('Halt in dummy mode will not finish this scan but abort!')
        self.steps = 0
        self.artificial_build_data = []
        return True

    def pause_scan(self, pause_bool=None):
        if pause_bool is None:
            pause_bool = not self.pause_bool
        logging.info('pausing the dummy, pause is: %s' % pause_bool)
        self.pause_bool = pause_bool
        return True

    def DeInitFpga(self, finalize_com=False):
        return True

    def FinalizeFPGACom(self):
        return True

    def set_stopVoltMeas(self, stop_bool):
        # Signal from ScanMain, that all dmms have a reading. Means we can simulate step complete and set new voltage.
        if stop_bool:
            self.steps -= 1
            if self.steps == 0:
                self.artificial_build_data.append(Form.add_header_to23_bit(1, int(b'0100', 2), 0, 1))  # step complete
                self.status = CsCfg.seqStateDict['measComplete']
            else:
                logging.debug('ContinousSequencerDummy done building artificial data. Going to measComplete state')
                self.artificial_build_data.append(Form.add_header_to23_bit(1, int(b'0100', 2), 0, 1))  # step complete
                self.artificial_build_data.append(Form.add_header_to23_bit(0, 3, 0, 1))  # means dac voltage set
        return True

    def read_outbits_state(self):
        return 0, 'dummy'

    def read_outbits_number_of_cmds(self):
        return 0, 0, 0
