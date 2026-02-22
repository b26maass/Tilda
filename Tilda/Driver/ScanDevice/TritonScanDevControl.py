"""
Created on 01.03.2019

@author: simkaufm

Module Description:
        This is a Triton device which will be able to control Scan Devices.

        Details see in class below
"""

import time
import logging
import sys
from PyQt5.QtCore import pyqtSignal

from Tilda.Driver.TritonListener.DummyTritonScanDevice import DummyScanDevice
from Tilda.Driver.TritonListener.TritonDeviceBase import DeviceBase
from Tilda.PolliFit import TildaTools as TiTs
from Tilda.Driver.ScanDevice.BaseTildaScanDeviceControl import BaseTildaScanDeviceControl
from Tilda.Driver.ScanDevice.NiUsb6225ScanDevice import NiUsb6225ScanDevice


class TritonScanDevControl(DeviceBase, BaseTildaScanDeviceControl):
    """
    This is a Triton device which will be able to control Scan Devices.

    It will be able to send commands to a designated scan device in order to tell this device
    the scan parameters and when to set the next step.
    In return, the scan device will tell the TritonScanDevControl, what scan parameters can be set
    and when it has set a new step.
    To control the scan device, the TritonScanDevControl will subscribe to the scan device
    and store the pyro-remote method in self.scan_dev.
    Therefore functions of the scan_dev can be accessed from the TritonScanDevControl directly,
    like "self.scan_dev.set_next_step()".
    The scan_dev, can therefore retunr values on these calls directly,
    but mostly it will use tha asynchrone self.send(ch, val) call,
    which will fire the self.receive in the TritonScanDevControl and there actions can be taken.
    This is a well established mechanism from within Triton at the moment.
    -> maybe as own device?! There is no need that one device can do both!?
    """
    # whenever the currently connected scan device is sending new values, this will be emitted.
    # dict, see in self.receive() -> 'devPars'
    scan_dev_sends_new_settings_pyqtsig = pyqtSignal(dict)
    # when the scan device has set the scan parameters it will emit a dictionary with the corresponding values
    # dict, see self.receive() -> 'scanParsSet'
    scan_dev_has_setup_these_pars_pyqtsig = pyqtSignal(dict)
    # when the scan device has set a new step, it will emit a dictionary
    # dict, see self.receive() -> 'scanProgress'
    scan_dev_has_set_a_new_step_pyqtsig = pyqtSignal(dict)

    ''' Device standard functions, do not delete! on, off, periodic, receive, load, emit'''
    '''Called when added'''

    def on(self, cfg):
        '''Setting necessary attributes, interval defaults to 0:'''

        self.type = 'TritonScanDevCtl'

        self.get_existing_callbacks_from_main()

        self.dummy_scan_dev = None  # will be initialized if db is set to local
        self.dummy_scan_dev_name = 'DummyScanDev'
        self.dummy_scan_dev_type = 'DummyScanDevice'
        if self.db == 'local':
            # create a dummy scan dev for testing
            self.create_dummy_scan_dev()

        self.scan_dev = None
        self.scan_dev_name = ''
        self.scan_dev_type = ''

        self.scan_dev_pars = {}  # {'step_size_min_max': (self.dev_min_step_size, self.dev_max_step_size),
        # 'set_val_min_max': (self.dev_min_val, self.dev_max_val), 'unit': self.start_step_units}
        self.scan_pars_set_from_dev = {}  # -> {'unit': self.start_step_units.name, 'start': self.sc_start,
        #  'stop': self.sc_stop, 'stepSize': self.sc_stepsize,
        # 'stepNums': self.sc_num_of_steps, 'valsArrrayOneScan': self.sc_one_scan_vals}

        self._request_next_step_from_scan_dev = False

    '''Called when removed'''

    def deinit_scan_dev(self):
        """ overwrite from mother class """
        self._stop()

    def off(self):
        """ called on _stop() """
        self.unsubscribe_from_scan_device()
        if self.dummy_scan_dev is not None:
            self.dummy_scan_dev._stop()
            self.dummy_scan_dev = None

    '''Called regularly, running in separate thread'''

    def periodic(self):
        # logging.debug('%s periodic is runnning, requesting step is: %s' % (self.name,
        #                                                                    self._request_next_step_from_scan_dev))
        if self._request_next_step_from_scan_dev:
            if self.scan_dev is not None:
                answ = self.scan_dev.setup_next_step()
                if answ:
                    # step is about to be set by the scan dev
                    self._request_next_step_from_scan_dev = False

    '''Called by subscriptors'''

    def receive(self, dev, t, ch, val):
        """
        called from subscriptors. Default calls from scanning devices:

        cH: scanParsSet val: dict, {
            'unit': self.start_step_units.name,
            'start': self.sc_start,
            'stop': self.sc_stop,
            'stepSize': self.sc_stepsize,
            'stepNums': self.sc_num_of_steps,
            'valsArrrayOneScan': self.sc_one_scan_vals}
        ch: scanProgress, val: dict,
            {
            'curStep': self.sc_l_cur_step,
            'curScan': self.sc_l_cur_scan,
            'percentOfScan': self.sc_l_perc_compl,
            'curStepVal': self.sc_one_scan_vals[self.sc_l_cur_step],
            'scanStatus': self.scan_status
        }
        ch: devPars, val: dict, {
            'step_size_min_max': (self.dev_min_step_size, self.dev_max_step_size),
            'set_val_min_max': (self.dev_min_val, self.dev_max_val),
            'unitName': self.start_step_units.name}

        :param dev: str, dev that has send the following
        :param t: str, timestamp
        :param ch: str, channel of the device
        :param val: anything that is serialisable, e.g. dict, list, etc.
        :return:
        """
        # logging.info('%s rcvd: %s' % (self.name, str((dev, t, ch, val))))
        if dev == self.scan_dev_name:  # usually anyhow only subscirbed to scan dev
            if ch == 'devPars':
                self.store_dev_pars(val)
            elif ch == 'scanProgress':
                self.scan_dev_has_set_next_step(val)
            elif ch == 'scanParsSet':
                self.store_scan_pars(val)

    '''Called when settings are loaded, vals contains setting dictionary'''

    def load(self, vals):
        pass

    '''Send current status on this command'''

    def emit(self):
        pass

    ''' comunication with scan dev '''
    ''' find available devs '''

    def available_scan_dev_types(self):
        """
        get available device types from the db, if local return dummy type
        :return: list of strings, ['dev_type1', 'dev_type2', ... ]
        """
        dev_types = []

        if self.db != 'local':
            # self.dbCur_execute(self.dbCur_execute("SELECT DeviceType FROM DeviceTypes ORDER BY DeviceType", None), None)
            self.dbCur_execute("SELECT DeviceType FROM DeviceTypes ORDER BY DeviceType", None)
            res = self.dbCur_fetchall()
            if res is not None:
                for dev_tuple in res:
                    dev_types.append(dev_tuple[0])
                #dev_types = res[0]
        else:
            logging.warning('no db connection, returning local DummyScanDev!')
            dev_types = [self.dummy_scan_dev_type, 'Matisse']

        ni_ao_channels = NiUsb6225ScanDevice.available_channels()
        if (ni_ao_channels or NiUsb6225ScanDevice._nidaq_available()) and \
                NiUsb6225ScanDevice.DEV_TYPE not in dev_types:
            dev_types.append(NiUsb6225ScanDevice.DEV_TYPE)
        return dev_types

    def available_scan_dev_names_by_type(self, dev_type):
        """
        return a list with the names of all currently available devices in the db.
        if db is set to local return the name of the DummyScanDev
        :return: list of strings, ['dev_name1', 'dev_name2', ... ]
        """
        dev_names = []

        if dev_type == NiUsb6225ScanDevice.DEV_TYPE:
            return NiUsb6225ScanDevice.available_channels()

        if self.db != 'local':
            self.dbCur_execute("SELECT deviceName FROM devices WHERE deviceType = %s", (dev_type,))
            res = self.dbCur_fetchall()
            if res is not None:
                if len(res):
                    dev_names = res[0]
        else:
            logging.warning('no db connection, returning local DummyScanDev!')
            dev_names = [self.dummy_scan_dev_name] if dev_type == self.dummy_scan_dev_type else ['MatisseDummy']
        return dev_names

    def create_dummy_scan_dev(self):
        """ cretae a dummy scan device for testing """
        self.dummy_scan_dev = DummyScanDevice(self.dummy_scan_dev_name, self.sql_conf)

    def subscribe_to_scan_dev(self, scan_dev_name, force_reconnect=False):
        """ subscribe to a scan dev by it's name in the Triton database """
        if self.scan_dev is not None:
            if self.scan_dev_name != scan_dev_name or force_reconnect:
                # unsubscribe first if already subscribed to something else or forced
                self.unsubscribe_from_scan_device()
            else:  # already subscibed, no need to do again
                self.get_scan_dev_settings()
                return None
        if self.db != 'local':
            self.scan_dev = self.subscribe(scan_dev_name)
        else:
            self.scan_dev = self.subscribe(self.dummy_scan_dev_name, self.dummy_scan_dev.uri)
        if self.scan_dev is None:
            logging.error('%s was not able to subscribe to the dev %s is it offline? will fail now' % (
                self.name, scan_dev_name))
        self.scan_dev_name = self.scan_dev.getName()
        self.scan_dev_type = self.scan_dev.getType()
        self.get_scan_dev_settings()

    def unsubscribe_from_scan_device(self):
        """ unsubscribe from the current scan device """
        self.unsubscribe(self.scan_dev_name)
        self.scan_dev = None
        self.scan_dev_name = ''
        self.scan_dev_type = ''
        self.scan_dev_pars = {}
        self.scan_pars_set_from_dev = {}

    def get_scan_dev_settings(self):
        """
        request the settings of the scan dev. This will emit its values and here it
        will be handled in self.receive()
        :return:
        """
        self.scan_dev.emit_device_parameters()

    def store_dev_pars(self, dev_pars_dict):
        """
        in receive, the scan deveice has published new settings
        -> send them upstream to gui etc.
        :param dev_pars_dict: dict, see in self.receive() -> 'devPars'
        :return:
        """
        self.scan_dev_pars = dev_pars_dict
        TiTs.print_dict_pretty(dev_pars_dict)
        self.scan_dev_sends_new_settings_pyqtsig.emit(self.scan_dev_pars)

    def return_stored_dev_pars(self):
        """
        return the device parameters of the current scan device.
        Those should have ben send by the device after subscribing.
        :return: dict, device parameters, might be empty of not stored yet.
        """
        return self.scan_dev_pars

    def setup_scan_in_scan_dev(self, start, stepsize, num_of_steps, num_of_scans, invert_in_odd_scans):
        """
        set these values in the scan device.
        Once this has completed setting this up, it will emit the scan pars
        and this can be handled her in the self.receive()
        :param start: float, starting point in units of self.start_step_units
        :param stepsize: float, step size in units of self.start_step_units
        :param num_of_steps: int, number of steps per scan
        :param num_of_scans: int, number of scans
        :param invert_in_odd_scans: bool, True -> invert after step complete
        :return: None
        """
        self._request_next_step_from_scan_dev = False
        self.scan_dev.setup_scan(start, stepsize, num_of_steps, num_of_scans, invert_in_odd_scans)

    def store_scan_pars(self, set_scan_pars_from_dev):
        """
        Once the device has set the scan settings it will return the coerced once.
        This will be send from here to upstream via a pyqtsignal!
        :param set_scan_pars_from_dev: dict, see self.receive() -> 'scanParsSet'
        """
        self.scan_pars_set_from_dev = set_scan_pars_from_dev
        self.scan_dev_has_setup_these_pars_pyqtsig.emit(self.scan_pars_set_from_dev)

    def scan_dev_has_set_next_step(self, scan_progress_dict):
        """
        wrapper for pyqtsignal and to store the scan progress
        :param scan_progress_dict: dict, see self.receive() -> 'scanProgress'
        """
        self.scan_prog_dict = scan_progress_dict
        self.scan_dev_has_set_a_new_step_pyqtsig.emit(self.scan_prog_dict)

    def request_next_step(self):
        """
        request the next step from the scan device from self.periodic.
        Even if the device is currently busy it will keep requesting until device answers.
        If meanwhile the function is called yet again, this call will get lost
            -> next step is called too often from upstream.
            -> here a warning is emitted but one has to make sure not to let this happen.
            -> always only call for the next step when the last one has been ensured to be set

        Might be called from pipeline by pyqtsignal or so.
        This will also start the scan after it has ben setup properly.

        :return: bool, True for success, False for failure.
        """
        if self._request_next_step_from_scan_dev:
            # will happen if the scan device still is setting the step and repeated calls for the step are coming in.
            # this must be avoided!
            logging.warning('Warning, %s was told to set the next step but'
                            ' it is still busy setting the last step, this call is ignored!' % self.name)
            return False
        else:
            self._request_next_step_from_scan_dev = True
            logging.debug('%s will from now on request the next step from the dev' % self.name)
            if self._interval <= 1.0:
                self.setInterval(0.1)
            return True

    def abort_scan(self):
        """
        abort the scan.
        """
        if self.scan_dev is not None:
            self.scan_dev.abort_scan()

    def set_pre_scan_masurement_setpoint(self, set_val):
        """
        Set the scan device to the setpoint, so a pre scan measurement can be performed with other devices.
        blocks until value is set.
        :param set_val: float, set point for the device
        :return: bool, True for success
        """
        ret = False
        if self.scan_dev is not None:
            ret = self.scan_dev.set_pre_scan_measurement_setpoint(set_val)
        return ret

    def return_scan_dev_info(self, dev_type=None, dev_name=None):
        """
        return the scan device info currently subscribed to
        or as requested by dev_type + dev_name
        :return dev_type: str, type of device or None for currently subscribed to
        :return dev_name: str, name of device for which the values are requested, None for currently subscribed to.
        :return dict: {
            'name': 'base',
            'type': 'base',  # what type of device, e.g. AD5781(DAC) / Matisse (laser)
            'devClass': 'base',  # carrier class of the dev, e.g. DAC / Triton
            'stepUnitName': Units.line_volts.name,
            'start': 0.0,
            'stop': 0.0,
            'stepSize': 1.0,
            'preScanSetPoint': None,  # 0 volts
            'postScanSetPoint': None,
            'timeout_s': 10.0,  # timeout in seconds after which step setting is accounted as failure due to timeout,
            # set top 0 for never timing out.
            'setValLimit': (-10.0, 10.0),
            'stepSizeLimit': (7.628880920000002e-05, 15.0)
        }
        """
        if dev_type == NiUsb6225ScanDevice.DEV_TYPE and (dev_name is None or dev_name == ''):
            ni_channels = NiUsb6225ScanDevice.available_channels()
            dev_name = ni_channels[0] if ni_channels else ''

        if dev_type is None and dev_name is None and self.scan_dev_pars != {}:
            # is subscribed to a scan_dev return real dev pars, otherwise return from storage
            dev_type = self.scan_dev_type
            dev_name = self.scan_dev_name
            set_val_lims = self.scan_dev_pars['set_val_min_max']
            step_min_max = self.scan_dev_pars['step_size_min_max']
            unit_name = self.scan_dev_pars['unitName']
        else:
            # get dev pars from storage (maybe db later?)
            pars_dict_stored = self.scan_dev_pars_storage_by_type(dev_type)
            set_val_lims = pars_dict_stored['set_val_min_max']
            step_min_max = pars_dict_stored['step_size_min_max']
            unit_name = pars_dict_stored['unitName']
        if self.scan_pars_set_from_dev != {}:
            #     'start': self.sc_start,
            #     'stop': self.sc_stop,
            #     'stepSize': self.sc_stepsize,
            start = self.scan_pars_set_from_dev['start']
            stop = self.scan_pars_set_from_dev['stop']
            stepsize = self.scan_pars_set_from_dev['stepSize']
        else:
            start = 0.0
            stop = 10.0
            stepsize = 1.0

        ret = {
            'name': dev_name,
            'type': dev_type,  # what type of device, e.g. AD5781(DAC) / Matisse (laser)
            'devClass': 'Triton',  # carrier class of the dev, e.g. DAC / Triton
            'stepUnitName': unit_name,
            'start': start,  # not used upstream !?
            'stop': stop,  # not used upstream !?
            'stepSize': stepsize,  # not used upstream !?
            'preScanSetPoint': None,  # not used upstream !?
            'postScanSetPoint': None,  # not used upstream !?
            'timeout_s': 10.0,  # timeout in seconds after which step setting is accounted as failure due to timeout,
            # set top 0 for never timing out.
            'setValLimit': set_val_lims,
            'stepSizeLimit': step_min_max
        }
        return ret

    def scan_dev_pars_storage_by_type(self, dev_type):
        """
        return device parameters from storage
        -> useful when not wanting to subscribe to the actual devs

        > keep up to date for desired scan devices :(
        > maybe get these from database later on?

        :param dev_type: str, type of the dev
        :return: dict,
        {'step_size_min_max': (self.dev_min_step_size, self.dev_max_step_size),
        'set_val_min_max': (self.dev_min_val, self.dev_max_val),
        'unitName': self.start_step_units.name}}
        """
        step_min_max = (- 1 * 10 ** 30, 1 * 10 ** 30)  # default
        set_val_min_max = (- 1 * 10 ** 30, 1 * 10 ** 30)  # default
        unit_name = self.possible_units.not_defined.name  # default
        if dev_type == 'Matisse':
            # overwrite for matisse
            step_min_max = (- 1 * 10 ** 30, 1 * 10 ** 30)  # default
            set_val_min_max = (- 1 * 10 ** 30, 1 * 10 ** 30)  # default
            unit_name = self.possible_units.frequency_mhz.name
        elif dev_type == 'Matisse_Dummy':
            # overwrite for matisse
            step_min_max = (- 1 * 10 ** 30, 1 * 10 ** 30)  # default
            set_val_min_max = (- 1 * 10 ** 30, 1 * 10 ** 30)  # default
            unit_name = self.possible_units.frequency_mhz.name
        elif dev_type == 'Scraper':
            # overwrite for scraper
            step_min_max = (0.02, 0.02)  # default
            set_val_min_max = (0, 150)  # default
            unit_name = self.possible_units.scraper_mm.name
        elif dev_type == self.dummy_scan_dev_type:
            step_min_max = (-10.0, 10.0)  # default
            set_val_min_max = (0.01, 10000000.0)  # default
            unit_name = self.possible_units.frequency_mhz.name
        elif dev_type == NiUsb6225ScanDevice.DEV_TYPE:
            step_min_max = NiUsb6225ScanDevice.STEP_SIZE_LIMIT
            set_val_min_max = NiUsb6225ScanDevice.SET_VAL_LIMIT
            unit_name = self.possible_units.line_volts.name

        # add more devs by elif

        ret_dict = {
            'step_size_min_max': step_min_max,
            'set_val_min_max': set_val_min_max,
            'unitName': unit_name}
        return ret_dict


# Testing:
if __name__ == '__main__':
    app_log = logging.getLogger()
    # app_log.setLevel(getattr(logging, args.log_level))
    app_log.setLevel(logging.INFO)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    # ch.setFormatter(log_formatter)
    app_log.addHandler(ch)

    app_log.info('****************************** starting ******************************')
    app_log.info('Log level set to DEBUG')


    sc_ctrl = TritonScanDevControl('ScanControlTestUnit')

    devs_db = sc_ctrl.available_scan_dev_types()
    print('available devs in db: ', devs_db)
    sc_ctrl.subscribe_to_scan_dev('')
    sc_ctrl.setup_scan_in_scan_dev(0, 10, 11, 50, False)
    sc_dev_inf = sc_ctrl.return_scan_dev_info()
    print('info from scan device: %s' % sc_dev_inf)
    sc_ctrl.set_pre_scan_masurement_setpoint(5)
    # calling next step too often will cause failures:
    # normal and must be avoid upstream by only requesting a
    # new step when the last one was confirmed to be set
    i = 0
    while i < 3:
        i += 1
        sc_ctrl.request_next_step()
        time.sleep(2.5)
    input('anything to stop')
    sc_ctrl._stop()
