"""

Created on '29.09.2015'

@author:'simkaufm'

"""

import ast
import logging
import os
from copy import deepcopy
import gc

from PyQt5 import QtCore
from PyQt5 import QtWidgets

import Tilda.Application.Config as Cfg
from Tilda.Application.Importer import DAC_Calibration
import Tilda.Service.Scan.ScanDictionaryOperations as SdOp
import Tilda.Service.VoltageConversions.VoltageConversions as VCon
from Tilda.Driver.ScanDevice.NiUsb6225ScanDevice import NiUsb6225ScanDevice
from Tilda.Driver.DataAcquisitionFpga.TriggerTypes import TriggerTypes as TiTs
from Tilda.Interface.TriggerWidgets import FindDesiredTriggerWidg
from Tilda.Interface.SequencerWidgets import FindDesiredSeqWidg
from Tilda.Interface.PulsePatternUi.PulsePatternUi import PulsePatternUi
from Tilda.Interface.SetVoltageUi.SetVoltageUi import SetVoltageUi
from Tilda.Interface.TrackParUi.Ui_TrackPar_Wide import Ui_MainWindowTrackPars
from Tilda.Interface.PreScanConfigUi.PreScanConfigUi import PreScanConfigUi
from Tilda.Interface.OutBitsUi.OutBitsUi import OutBitsUi
from Tilda.PolliFit.Measurement.SpecData import SpecDataXAxisUnits as Units
import Tilda.Service.Scan.draftScanParameters as dft


class TrackUi(QtWidgets.QMainWindow, Ui_MainWindowTrackPars):
    track_ui_call_back_signal = QtCore.pyqtSignal(dict)

    outbits_confirmed_signal = QtCore.pyqtSignal(dict)

    def __init__(self, scan_ctrl_win, track_number, active_iso_name, main_gui):
        """
        Non modal Main window to determine the scanparameters for a single track of a given isotope.
        scan_ctrl_win is needed for writing the track dictionary to a given scan dictionary.
        track_number is the number of the track which will be worked on.
        default_track_dict is the default dictionary which will be deepcopied and then worked on.
        """
        super(TrackUi, self).__init__()
        os.chdir(os.path.dirname(__file__))  # necessary for the icons to appear

        self.track_name = 'track' + str(track_number)

        self.scan_ctrl_win = scan_ctrl_win
        if scan_ctrl_win is None:
            self.active_iso = 'None_trs'
        else:
            self.active_iso = scan_ctrl_win.active_iso
        self.subscription_name = self.active_iso + '_' + self.track_name
        self.seq_type = self.active_iso.split('_')[-1]
        self.track_number = track_number
        self.main_gui = main_gui

        self._scan_main_for_debugging = None  # one can load a scan_main to this in
        # order to debug the TrackUi independent

        if Cfg._main_instance is not None:
            self.buffer_pars = deepcopy(Cfg._main_instance.scan_pars.get(active_iso_name).get(self.track_name))
        else:
            self.buffer_pars = deepcopy(dft.draftTrackPars)
            from Tilda.Service.Scan.ScanMain import ScanMain
            self._scan_main_for_debugging = ScanMain()
        # add scan device if not present:
        if self.buffer_pars.get('scanDevice', None) is None:
            self.buffer_pars['scanDevice'] = deepcopy(dft.draft_scan_device)
        self._canonicalize_legacy_scan_device_labels(self.buffer_pars.get('scanDevice', {}))

        logging.info('%s parameters are: %s ' % (self.track_name, self.buffer_pars))
        if self._uses_internal_fpga_dac_quantization():
            # is needed to be able to fix stop
            self.scan_dev_stop_by_user = self.calc_scan_dev_stop_val()
        else:
            self.scan_dev_stop_by_user = 0

        self.track_ui_call_back_signal.connect(self.refresh_pow_sup_readback)
        self.set_volt_win = None

        self.setupUi(self)

        if self.scan_ctrl_win is not None:
            self.setWindowTitle(self.scan_ctrl_win.win_title + '_' + self.track_name)

        """ sequencer specific """
        self.sequencer_widget = FindDesiredSeqWidg.find_sequencer_widget(self.seq_type, self.buffer_pars, self.main_gui)
        self.verticalLayout.replaceWidget(self.specificSequencerSettings, self.sequencer_widget)
        if self.seq_type == 'kepco':
            self.spinBox_nOfScans.setMaximum(1)

        """ Trigger related """
        if self.buffer_pars['trigger'].get('meas_trigger', None) is None:
            # seems to be an isotope created before the advanced triggers were introduced
            old_version_trigger = self.buffer_pars['trigger']
            self.buffer_pars['trigger'] = {'meas_trigger': old_version_trigger,
                                           'step_trigger': {},
                                           'scan_trigger': {}}
        self.tabWidget.setCurrentIndex(0)  # Always step trigger as active tab, since this is the standard "trigger"
        # Measurement Trigger
        self.checkBox_UseAllTracks.setDisabled(True)
        self.checkBox_UseAllTracks.setToolTip('not yet included')
        self.trigger_widget = None
        self.update_trigger_combob()
        self.trigger_widget = FindDesiredTriggerWidg.find_trigger_widget(self.buffer_pars.get('trigger', {})
                                                                         .get('meas_trigger', {}))
        self.trigger_vert_layout.replaceWidget(self.widget_trigger_place_holder, self.trigger_widget)
        self.comboBox_triggerSelect.currentTextChanged.connect(self.trigger_select)
        # Step Trigger
        self.checkBox_stepUseAllTracks.setDisabled(True)
        self.checkBox_stepUseAllTracks.setToolTip('not yet included')
        self.step_trigger_widget = None
        self.update_step_trigger_combob()
        self.step_trigger_widget = FindDesiredTriggerWidg.find_trigger_widget(self.buffer_pars.get('trigger', {})
                                                                              .get('step_trigger', {}))
        self.step_trigger_vert_layout.replaceWidget(self.widget_step_trigger_place_holder, self.step_trigger_widget)
        self.comboBox_stepTriggerSelect.currentTextChanged.connect(self.step_trigger_select)
        # Scan Trigger
        self.checkBox_scanUseAllTracks.setDisabled(True)
        self.checkBox_scanUseAllTracks.setToolTip('not yet included')
        self.scan_trigger_widget = None
        self.update_scan_trigger_combob()
        self.scan_trigger_widget = FindDesiredTriggerWidg.find_trigger_widget(self.buffer_pars.get('trigger', {})
                                                                              .get('scan_trigger', {}))
        self.scan_trigger_vert_layout.replaceWidget(self.widget_scan_trigger_place_holder, self.scan_trigger_widget)
        self.comboBox_scanTriggerSelect.currentTextChanged.connect(self.scan_trigger_select)

        """ pulse pattern related """
        self.pulse_pattern_win = None
        self.pushButton_config_pulse_pattern.clicked.connect(self.open_pulse_pattern_window)

        """ pre post scan measurement related """
        self.pre_post_scan_window = None
        self.pushButton_conf_pre_post_tr_meas.clicked.connect(self.open_pre_post_conf_win)

        """ outbit related """
        self.outbit_win = None
        self.pushButton_con_outbits.clicked.connect(self.open_outbits_win)
        self.outbits_confirmed_signal.connect(self.received_new_outbit_dict)

        """Scan dev related top to bottom as in gui """
        self.comboBox_scanDevClass.addItems(dft.scan_dev_classes_available)
        self.comboBox_scanDevClass.currentTextChanged.connect(self.scan_dev_class_changed)
        self.comboBox_scanDev_type.currentTextChanged.connect(self.scan_type_changed)
        self.comboBox_scanDev_name.currentTextChanged.connect(self.scan_dev_name_changed)

        self.stored_scan_dev_from_init = deepcopy(self.buffer_pars['scanDevice'])

        self.doubleSpinBox_scanDev_timeout_s.valueChanged.connect(self.scan_dev_timeout_set)
        self.doubleSpinBox_scanDev_timeout_s.setRange(0., 21.0)  # 21 s currently limit res is 10ns

        self.doubleSpinBox_scanDevStart.valueChanged.connect(self.scan_dev_start_v_set)
        self.doubleSpinBox_scanDevStop.valueChanged.connect(self.scan_dev_stop_v_set)
        self.doubleSpinBox_scanDevStepSize.valueChanged.connect(self.scan_dev_step_size_set)
        
        self.doubleSpinBox_scanDevPreScan.valueChanged.connect(self.scan_dev_pre_scan_val_set)
        self.pushButton_scanDev_pre_sc_copy_from_start.clicked.connect(self.scan_dev_pre_val_copy_clicked)
        self.checkBox_scanDev_setPreScan.stateChanged.connect(self.scan_dev_pre_scan_set_checkbox_clicked)

        self.doubleSpinBox_scanDevPostScan.valueChanged.connect(self.scan_dev_post_scan_val_set)
        self.pushButton_scanDev_post_ssc_copy_stop.clicked.connect(self.scan_dev_post_val_copy_clicked)
        self.checkBox_scanDev_setPostScan.stateChanged.connect(self.scan_dev_post_scan_set_checkbox_clicked)

        self.spinBox_nOfSteps.setRange(2, 2 ** 20)
        self.spinBox_nOfSteps.valueChanged.connect(self.n_of_steps_set)
        self.spinBox_nOfScans.valueChanged.connect(self.n_of_scans_set)
        self.checkBox_invertScan.stateChanged.connect(self.invert_scan_set)

        """post acceleration controls:"""
        self.comboBox_postAccOffsetVoltControl.currentIndexChanged.connect(self.post_acc_offset_volt_control_set)
        self.doubleSpinBox_postAccOffsetVolt.valueChanged.connect(self.post_acc_offset_volt)

        """Scaler selection:"""
        self.lineEdit_activePmtList.textChanged.connect(self.active_pmt_list_set)

        """collinear/anticollinear"""
        self.checkBox_colDirTrue.stateChanged.connect(self.col_dir_true_set)

        """Buttons:"""
        self.pushButton_cancel.clicked.connect(self.cancel)
        self.pushButton_confirm.clicked.connect(self.confirm)
        self.pushButtonResetToDefault.clicked.connect(self.reset_to_default)
        self.pushButton_postAccOffsetVolt.clicked.connect(self.set_voltage)

        """Advanced Settings:"""
        self.doubleSpinBox_waitAfterReset_muS.valueChanged.connect(self.wait_after_reset_mu_sec_set)
        self.doubleSpinBox_waitForKepco_muS.valueChanged.connect(self.wait_for_kepco_mu_sec)

        self.set_labels_by_dict(self.buffer_pars)
        if Cfg._main_instance is not None:
            Cfg._main_instance.subscribe_to_power_sub_status(self.track_ui_call_back_signal, self.subscription_name)
        self.show()

    """functions:"""

    def set_labels_by_dict(self, track_dict):
        """" the values in the track_dict will be written to the corresponding spinboxes,
        which will call the connected functions.
        Each function is tried separately in order to give the next one a chance of execution,
        when default val is messed up.
        """
        cb_post_acc_ind_before_load = self.comboBox_postAccOffsetVoltControl.currentIndex()
        logging.info('setting trackui labels by dict: %s' % str(track_dict))
        scan_dev_dict = track_dict.get('scanDevice', dft.draft_scan_device)
        self._canonicalize_legacy_scan_device_labels(scan_dev_dict)
        logging.debug('scan dev settings in this track dict: %s' % str(track_dict['scanDevice']))
        try:
            func_list = [
                # (self.doubleSpinBox_dwellTime_ms.setValue,
                #  self.check_for_none(track_dict.get('dwellTime10ns'), 0) * (10 ** -5)),
                (self.scan_dev_class_changed,
                 self.check_for_none(scan_dev_dict.get('devClass'), 'DAC')),
                (self.scan_type_changed,
                 self.check_for_none(scan_dev_dict.get('type'), 'AD57X1(DAC)')),
                (self.scan_dev_name_changed,
                 self.check_for_none(scan_dev_dict.get('name'), '')),
                (self.scan_dev_timeout_set,
                 self.check_for_none(scan_dev_dict.get('timeout_s'), 0)),
                (self.scan_dev_start_v_set,
                 self.check_for_none(scan_dev_dict.get('start'), 0.1)),
                (self.scan_dev_stop_v_set,
                 self.check_for_none(scan_dev_dict.get('stop'), 2 ** 18)),
                (self.scan_dev_step_size_set,
                 self.check_for_none(track_dict.get('stepSize'), 0)),
                (self.scan_dev_pre_scan_val_set,
                 scan_dev_dict.get('preScanSetPoint')),
                (self.scan_dev_post_scan_val_set,
                 scan_dev_dict.get('postScanSetPoint')),
                (self.spinBox_nOfScans.setValue, self.check_for_none(track_dict.get('nOfScans'), 0)),
                (self.checkBox_invertScan.setChecked, self.check_for_none(track_dict.get('invertScan'), False)),
                (self.invert_scan_set, self.check_for_none(track_dict.get('invertScan'), False)),
                (self.comboBox_postAccOffsetVoltControl.setCurrentIndex,
                 int(self.check_for_none(track_dict.get('postAccOffsetVoltControl'), 0))),
                (self.doubleSpinBox_postAccOffsetVolt.setValue,
                 self.check_for_none(track_dict.get('postAccOffsetVolt'), 0)),
                (self.lineEdit_activePmtList.setText,
                 str(self.check_for_none(track_dict.get('activePmtList'), [0]))[1:-1]),
                (self.checkBox_colDirTrue.setChecked, self.check_for_none(track_dict.get('colDirTrue'), False)),
                (self.col_dir_true_set, self.check_for_none(track_dict.get('colDirTrue'), False)),
                (self.doubleSpinBox_waitAfterReset_muS.setValue,
                 self.check_for_none(track_dict.get('waitAfterReset1us'), 0)),
                (self.doubleSpinBox_waitForKepco_muS.setValue,
                 self.check_for_none(track_dict.get('waitForKepco1us'), 0)),
                (self.spinBox_nOfSteps.setValue, self.check_for_none(track_dict.get('nOfSteps'), 0))
            ]
        except Exception as e:
            logging.error('error while creating function calls in TrackUi: %s' % e, exc_info=True)
        for func in func_list:
            try:
                func[0](func[1])
            except Exception as e:
                logging.error('error while loading default track dictionary: ' + str(e), exc_info=True)
        # self.comboBox_postAccOffsetVoltControl.currentIndexChanged.emit(self.comboBox_postAccOffsetVoltControl.currentIndex())
        logging.info('setting trackui labels by dict is done postAccOffsetVoltControl is: ' + str(
            self.buffer_pars['postAccOffsetVoltControl']))
        if cb_post_acc_ind_before_load == self.comboBox_postAccOffsetVoltControl.currentIndex():
            # force index change emit if the index was not changed by loading
            self.comboBox_postAccOffsetVoltControl.currentIndexChanged.emit(
                int(self.check_for_none(track_dict.get('postAccOffsetVoltControl'), 0)))

    def check_for_none(self, check, replace):
        """
        checks if param "check" is None and replaces it if it is None
        """
        if check is None:
            check = replace
        return check

    def _canonicalize_legacy_scan_device_labels(self, scan_dev):
        """
        Normalize legacy scan-device labels for UI display and saving.
        Keeps old scans loadable while avoiding duplicate combobox entries.
        """
        if not isinstance(scan_dev, dict):
            return

        # Legacy scans may store the local NI USB-6225 under Triton.
        if scan_dev.get('type', '') == NiUsb6225ScanDevice.DEV_TYPE and scan_dev.get('devClass', '') == 'Triton':
            scan_dev['devClass'] = 'DAC'

        # Legacy internal DAC labels used "AD5781" / "AD5781_Ser1"; canonicalize to the
        # current AD57X1 label and configured DAC name so the UI shows only one entry.
        legacy_dac_types = {'AD5781', 'AD57X1'}
        canonical_dac_type = 'AD57X1(DAC)'
        if scan_dev.get('devClass', 'DAC') == 'DAC':
            if scan_dev.get('type', '') in legacy_dac_types:
                scan_dev['type'] = canonical_dac_type
            if scan_dev.get('type', '') == canonical_dac_type and scan_dev.get('name', '') in {'', 'AD5781_Ser1'}:
                scan_dev['name'] = DAC_Calibration.dac_name

    def _uses_internal_fpga_dac_quantization(self):
        """
        UI bit/step rounding applies only to the internal FPGA DAC, not the NI USB-6225 AO.
        """
        scan_dev = self.buffer_pars.get('scanDevice', {})
        if scan_dev.get('devClass', 'DAC') != 'DAC':
            return False
        return scan_dev.get('type', '') != NiUsb6225ScanDevice.DEV_TYPE

    def update_trigger_combob(self, default_trig=None):
        """
        updates the trigger combo box by looking up the members of the enum
        """
        self.comboBox_triggerSelect.addItems([tr.name for tr in TiTs])
        if default_trig is None:
            trig_type = self.buffer_pars.get('trigger', {}).get('meas_trigger', {}).get('type', TiTs.no_trigger)
            self.comboBox_triggerSelect.setCurrentText(trig_type.name)

    def update_step_trigger_combob(self, default_trig=None):
        """
        updates the step trigger combo box by looking up the members of the enum
        """
        self.comboBox_stepTriggerSelect.addItems([tr.name for tr in TiTs])
        if default_trig is None:
            trig_type = self.buffer_pars.get('trigger', {}).get('step_trigger', {}).get('type', TiTs.no_trigger)
            self.comboBox_stepTriggerSelect.setCurrentText(trig_type.name)

    def update_scan_trigger_combob(self, default_trig=None):
        """
        updates the scan trigger combo box by looking up the members of the enum
        """
        self.comboBox_scanTriggerSelect.addItems([tr.name for tr in TiTs])
        if default_trig is None:
            trig_type = self.buffer_pars.get('trigger', {}).get('scan_trigger', {}).get('type', TiTs.no_trigger)
            self.comboBox_scanTriggerSelect.setCurrentText(trig_type.name)

    def trigger_select(self, trig_str):
        """
        finds the desired trigger widget and sets it into self.trigger_widget
        """
        self.buffer_pars['trigger']['meas_trigger']['type'] = getattr(TiTs, trig_str)
        self.trigger_vert_layout.removeWidget(self.trigger_widget)
        if self.trigger_widget is not None:
            self.trigger_widget.setParent(None)
        self.trigger_widget = FindDesiredTriggerWidg.find_trigger_widget(self.buffer_pars.get('trigger', {})
                                                                         .get('meas_trigger', {}))
        self.trigger_vert_layout.addWidget(self.trigger_widget)

    def step_trigger_select(self, trig_str):
        """
        finds the desired step trigger widget and sets it into self.step_trigger_widget
        """
        self.buffer_pars.get('trigger', {}).get('step_trigger', {})['type'] = getattr(TiTs, trig_str)
        self.step_trigger_vert_layout.removeWidget(self.step_trigger_widget)
        if self.step_trigger_widget is not None:
            self.step_trigger_widget.setParent(None)
        self.step_trigger_widget = FindDesiredTriggerWidg.find_trigger_widget(self.buffer_pars.get('trigger', {})
                                                                              .get('step_trigger', {}))
        self.step_trigger_vert_layout.addWidget(self.step_trigger_widget)

    def scan_trigger_select(self, trig_str):
        """
        finds the desired scan trigger widget and sets it into self.scan_trigger_widget
        """
        self.buffer_pars.get('trigger', {}).get('scan_trigger', {})['type'] = getattr(TiTs, trig_str)
        self.scan_trigger_vert_layout.removeWidget(self.scan_trigger_widget)
        if self.scan_trigger_widget is not None:
            self.scan_trigger_widget.setParent(None)
        self.scan_trigger_widget = FindDesiredTriggerWidg.find_trigger_widget(self.buffer_pars.get('trigger', {})
                                                                              .get('scan_trigger', {}))
        self.scan_trigger_vert_layout.addWidget(self.scan_trigger_widget)

    """ pulse pattern related """

    def open_pulse_pattern_window(self):
        if self.pulse_pattern_win is not None and self.main_gui is not None:
            self.main_gui.raise_win_to_front(self.pulse_pattern_win)
        else:
            self.pulse_pattern_win = PulsePatternUi(self.active_iso, self.track_name, self.main_gui, self)
        cmd_list = self.buffer_pars.get('pulsePattern', {}).get('cmdList', [])
        per_list = self.buffer_pars.get('pulsePattern', {}).get('periodicList', [])
        simple_dict = self.buffer_pars.get('pulsePattern', {}).get('simpleDict', [])
        if per_list:
            self.pulse_pattern_win.load_periodic(per_list)
            # overwrite cmd_list in order to setup from periodic list! -> this will anyhow update the list view
            # if there is a periodic list stored in the db, use this otherwise setup from cmd_list!
            cmd_list = []
        if cmd_list:
            self.pulse_pattern_win.cmd_list_to_gui(cmd_list)
        if simple_dict:
            self.pulse_pattern_win.load_simple_dict(simple_dict)

    def close_pulse_pattern_window(self):
        self.pulse_pattern_win = None

    """ pre post scan meas related """

    def open_pre_post_conf_win(self):
        """ open a new pre post scan config win or raise an existing one to front"""
        if self.pre_post_scan_window is None:
            self.pre_post_scan_window = PreScanConfigUi(self, self.active_iso, self.track_name)
        else:
            self.raise_win_to_front(self.pre_post_scan_window)

    def close_pre_post_scan_win(self):
        """ pre post scan window was closed, remove reference """
        self.pre_post_scan_window = None

    """ outbits related """

    def open_outbits_win(self):
        """ open outbit config won or raise to front """
        if self.outbit_win is None:
            self.outbit_win = OutBitsUi(self, deepcopy(self.buffer_pars.get('outbits', {})), self.outbits_confirmed_signal)
            self.outbit_win.destroyed.connect(self.outbit_win_closed)
        else:
            self.raise_win_to_front(self.outbit_win)
        logging.info('opened outbit win in iso %s for track %s' % (self.active_iso, self.track_name))

    def received_new_outbit_dict(self, outbit_dict):
        """ when gui clicks ok this should be emitted """
        self.buffer_pars['outbits'] = deepcopy(outbit_dict)
        logging.debug('trackUi of iso %s for track %s received outbit dict: %s'
                      % (self.active_iso, self.track_name, self.buffer_pars['outbits']))

    def outbit_win_closed(self):
        """ outbit win was closed -> remove from namespace """
        del self.outbit_win
        self.outbit_win = None
        gc.collect()
        logging.info('closed outbit win in iso %s for track %s' % (self.active_iso, self.track_name))

    '''scan device related: '''
    def scan_dev_class_changed(self, scan_dev_class_str):
        """ the scan dev was changed in the combobox -> fill available types and names """
        self.comboBox_scanDev_type.clear()
        self.buffer_pars['scanDevice']['devClass'] = scan_dev_class_str
        self.comboBox_scanDevClass.blockSignals(True)
        self.comboBox_scanDevClass.setCurrentText(scan_dev_class_str)
        self.comboBox_scanDevClass.blockSignals(False)
        # if no scan_main is around return this:
        if Cfg._main_instance is not None:
            Cfg._main_instance.scan_main.select_scan_dev_by_class(scan_dev_class_str)
            dev_types = Cfg._main_instance.scan_main.scan_dev.available_scan_dev_types()
        else:
            self._scan_main_for_debugging.select_scan_dev_by_class(scan_dev_class_str)
            dev_types = self._scan_main_for_debugging.scan_dev.available_scan_dev_types()
        if self.stored_scan_dev_from_init['devClass'] == scan_dev_class_str:
            # the device might not be available
            st_type = self.stored_scan_dev_from_init['type']
            if st_type not in dev_types and st_type:
                dev_types += [st_type]
        self.comboBox_scanDev_type.addItems(dev_types)
        self.scan_type_changed(self.comboBox_scanDev_type.currentText())

    def scan_type_changed(self, scan_type):
        """ when the combobox for the scan_dev_type is changed, this is called """
        self.buffer_pars['scanDevice']['type'] = scan_type
        self.comboBox_scanDev_type.blockSignals(True)
        self.comboBox_scanDev_type.setCurrentText(scan_type)
        self.comboBox_scanDev_type.blockSignals(False)
        self.comboBox_scanDev_name.clear()
        if Cfg._main_instance is not None:
            dev_names = Cfg._main_instance.scan_main.scan_dev.available_scan_dev_names_by_type(scan_type)
        else:
            dev_names = self._scan_main_for_debugging.scan_dev.available_scan_dev_names_by_type(scan_type)
        if self.stored_scan_dev_from_init['devClass'] == self.comboBox_scanDevClass.currentText():
            if self.stored_scan_dev_from_init['type'] == scan_type:
                # the device might not be available
                if self.stored_scan_dev_from_init['name'] not in dev_names:
                    dev_names += [self.stored_scan_dev_from_init['name']]
        self.comboBox_scanDev_name.addItems(dev_names)
        self.scan_dev_name_changed(self.comboBox_scanDev_name.currentText())

    def scan_dev_name_changed(self, sc_dev_name):
        """
        call this when the name of the scan device is changed
        will resolve the chosen devices unit
        """
        self.buffer_pars['scanDevice']['name'] = sc_dev_name
        self.comboBox_scanDev_name.blockSignals(True)
        self.comboBox_scanDev_name.setCurrentText(sc_dev_name)
        self.comboBox_scanDev_name.blockSignals(False)
        # if no scan_main is around return this:
        if Cfg._main_instance is not None:
            scan_dev_info = Cfg._main_instance.scan_main.scan_dev.return_scan_dev_info(
                self.buffer_pars['scanDevice']['type'], sc_dev_name)
        else:
            scan_dev_info = self._scan_main_for_debugging.scan_dev.return_scan_dev_info(
                self.buffer_pars['scanDevice']['type'], sc_dev_name)
        self.scan_dev_info_changed(scan_dev_info)

    def scan_dev_info_changed(self, scan_dev_info):
        """
        The info of the scan device has been returned
        -> set the units the device has
        -> set the limitations in start / stop / step
        -> ignore all other feedback for now. might be helpful what the device has
        coerced start / stop to later on but ignore for now
        :param scan_dev_info: dict, see Service/Scan/draftScanParameters.py:111
        currently:
        draft_scan_device = {
            'name': 'AD5781_Ser1',
            'type': 'AD5781',  # what type of device, e.g. AD5781(DAC) / Matisse (laser)
            'devClass': 'DAC',  # carrier class of the dev, e.g. DAC / Triton
            'stepUnitName': Units.line_volts.name,  # name if the SpecDataXAxisUnits
            'start': 0.0,  # in units of stepUnitName
            'stepSize': 1.0,  # in units of stepUnitName
            'stop': 5.0,  # in units of stepUnitName
            'preScanSetPoint': None,  # in units of stepUnitName, choose None if nothing should happen
            'postScanSetPoint': None,  # in units of stepUnitName, choose None if nothing should happen
            'timeout_s': 10.0,  # timeout in seconds after which step setting is accounted as failure due to timeout,
            # set top 0 for never timing out.
            'setValLimit': (-10.0, 10.0),
            'stepSizeLimit': (7.628880920000002e-05, 15.0)
        }
        :return: None
        """
        unit_name = scan_dev_info.get('stepUnitName', Units.not_defined.name)
        self.buffer_pars['scanDevice']['stepUnitName'] = unit_name
        self.label_scanDev_unit.setText(Units[unit_name].value)
        set_val_limits = scan_dev_info.get('setValLimit', (-15.0, 15.0))
        set_val_limits = [-lim/abs(lim)*(-abs(lim)//1) for lim in set_val_limits]  # [-9.99, 9.99] should be [-10, 10]
        self.doubleSpinBox_scanDevPostScan.setRange(*set_val_limits)
        self.doubleSpinBox_scanDevPreScan.setRange(*set_val_limits)
        self.doubleSpinBox_scanDevStop.setRange(*set_val_limits)
        self.doubleSpinBox_scanDevStart.setRange(*set_val_limits)
        self.buffer_pars['scanDevice']['setValLimit'] = set_val_limits
        step_limits = scan_dev_info.get('stepSizeLimit', (7.628880920000002e-05, 15.0))
        self.doubleSpinBox_scanDevStepSize.setRange(*step_limits)
        self.buffer_pars['scanDevice']['stepSizeLimit'] = step_limits

    def scan_dev_timeout_set(self, timeout_s):
        """ set the timeout in the buffer pars """
        self.buffer_pars['scanDevice']['timeout_s'] = timeout_s
        self.doubleSpinBox_scanDev_timeout_s.blockSignals(True)
        self.doubleSpinBox_scanDev_timeout_s.setValue(timeout_s)
        self.doubleSpinBox_scanDev_timeout_s.blockSignals(False)

    def scan_dev_start_v_set(self, start_val):
        """ this will write the doublespinbox value to the working dict and set the label
        it will also call recalc_step_stop to adjust the stepsize and then fine tune the stop value """
        if self._uses_internal_fpga_dac_quantization():
            # calculate everything according to the DAC and keep 18Bits in mind!
            start_18bit = VCon.get_nbits_from_voltage(start_val)
            start_val = VCon.get_voltage_from_bits(start_18bit)  # overwrite start_val with nearest possible val
            self.label_dacStartV_set.setText(str(round(start_val, 8)) + ' | ' + str(start_18bit))
            self.label_kepco_start.setText(str(round(start_val * 50, 2)))
        else:
            self.label_dacStartV_set.setText('%.8f' % start_val)
            self.label_kepco_start.setText('')
        self.doubleSpinBox_scanDevStart.blockSignals(True)
        self.doubleSpinBox_scanDevStart.setValue(start_val)
        self.doubleSpinBox_scanDevStart.blockSignals(False)
        self.buffer_pars['scanDevice']['start'] = start_val  # set start val in units of dev
        # for other device just set the start and recalc stop + n_of_steps
        self.recalc_n_of_steps_stop()

    def scan_dev_stop_v_set(self, stop_val):
        """
        this will write the doublespinbox value to the working dict and set the label
        it will also call recalc_n_of_steps_stop to adjust the number of steps and then fine tune the stop value
        """
        self.scan_dev_stop_by_user = deepcopy(stop_val)  # only touch this when double spinbox is touched
        self.buffer_pars['scanDevice']['stop'] = stop_val  # set stop val in units of dev
        self.recalc_n_of_steps_stop()

    def display_stop(self, stop):
        """ function only for displaying the stop value """
        if self._uses_internal_fpga_dac_quantization():
            stop_18bit = VCon.get_nbits_from_voltage(stop)
            stop = VCon.get_voltage_from_bits(stop_18bit)
            self.label_dacStopV_set.setText(str(round(stop, 8)) + ' | ' + str(stop_18bit))
            self.label_kepco_stop.setText(str(round(stop * 50, 2)))
        else:
            self.label_dacStopV_set.setText('%.8f' % stop)
            self.label_kepco_stop.setText('')
        self.doubleSpinBox_scanDevStop.blockSignals(True)
        self.doubleSpinBox_scanDevStop.setValue(stop)
        self.doubleSpinBox_scanDevStop.blockSignals(False)
        self.buffer_pars['scanDevice']['stop'] = stop

    def recalc_n_of_steps_stop(self):
        """ start and stop should be more or less constant if the stepsize changes,
        the number of steps must be adjusted.
        after adjusting the number of steps, the stop voltage is fine tuned to the next possible value.
        """
        try:
            self.display_step_size(self.buffer_pars['scanDevice']['stepSize'])
            self.display_n_of_steps(self.calc_n_of_steps())
            stop = self.calc_scan_dev_stop_val()
            stop_eq_start = stop == self.buffer_pars['scanDevice']['start']
            stop_bel_range = stop <= self.buffer_pars['scanDevice']['setValLimit'][0]
            stop_above_range = stop >= self.buffer_pars['scanDevice']['setValLimit'][1]
            if stop_eq_start or stop_above_range or stop_bel_range:
                logging.debug('stop will not properly be displayed,'
                              ' stop_eq_start = %s stop_above_range = %s  stop_bel_range= %s range: %s' % (
                    stop_eq_start, stop_above_range,
                    stop_bel_range, str(self.buffer_pars['scanDevice']['setValLimit'])
                ))
                return False
            self.display_stop(stop)
            return True
        except Exception as e:
            logging.error('the following error occurred while calculating the number of steps:'
                          + str(e))

    def calc_scan_dev_stop_val(self):
        """ calculates the dac stop value: stop = start + step * (steps-1) """
        try:
            start = self.check_for_none(self.buffer_pars['scanDevice'].get('start', None), 0)
            step = self.check_for_none(self.buffer_pars['scanDevice'].get('stepSize', None), 1)
            num_of_steps = self.check_for_none(self.buffer_pars['nOfSteps'], 1)
            stop = start + step * (num_of_steps - 1)
            if self._uses_internal_fpga_dac_quantization():
                start_18b = VCon.get_nbits_from_voltage(start)  # change to bits first
                step_18bit = VCon.get_nbit_stepsize(step)
                stop_18bit = VCon.calc_dac_stop_18bit(start_18b, step_18bit, num_of_steps)
                stop = VCon.get_voltage_from_bits(stop_18bit)

        except Exception as e:
            logging.error('following error occurred while calculating the stop value:' + str(e))
            stop = 0
        return stop

    def calc_step_size(self):
        """ calculates the stepsize: (stop - start) / nOfSteps  """
        try:
            start = self.check_for_none(self.buffer_pars['scanDevice'].get('start'), 0)
            stop = self.scan_dev_stop_by_user
            steps = self.check_for_none(self.buffer_pars.get('nOfSteps'), 1)
            try:
                dis = stop - start
                stepsize = dis / (steps - 1)
            except ZeroDivisionError:
                stepsize = 0
            if self._uses_internal_fpga_dac_quantization():
                # for DAC bitwise calc!
                start_18b = VCon.get_nbits_from_voltage(start)  # change to bits first
                stop_18b = VCon.get_nbits_from_voltage(stop)
                stepsize_18bit = VCon.calc_step_size(start_18b, stop_18b, steps)  # int calculation
                stepsize = VCon.get_stepsize_in_volt_from_bits(stepsize_18bit)  # aaaand back again
        except Exception as e:
            logging.error('following error occurred while calculating the stepsize:' + str(e))
            stepsize = 0
        return stepsize

    def scan_dev_pre_scan_val_set(self, pre_scan_set_val, blck_chbox_sig=False):
        """
        value which will be set before the scan in the prescan measurement
        it will aslo set teh checkbox next to it!
        :param pre_scan_set_val: float, unit is same as step etc. 
                                    use None for not measuring
        """ 
        self.buffer_pars['scanDevice']['preScanSetPoint'] = pre_scan_set_val
        ch_state = QtCore.Qt.CheckState.Checked if pre_scan_set_val is not None else QtCore.Qt.CheckState.Unchecked
        self.scan_dev_pre_scan_set_checkbox_clicked(ch_state, block_signal=True)
        if pre_scan_set_val is not None:
            self.doubleSpinBox_scanDevPreScan.blockSignals(True)
            self.doubleSpinBox_scanDevPreScan.setValue(pre_scan_set_val)
            self.doubleSpinBox_scanDevPreScan.blockSignals(False)

    def scan_dev_post_scan_val_set(self, post_scan_set_val, blck_chbox_sig=False):
        """
        value which will be set before the scan in the postscan measurement
        :param post_scan_set_val: float, unit is same as step etc.
                                    use None for not measuring
        """
        self.buffer_pars['scanDevice']['postScanSetPoint'] = post_scan_set_val
        ch_state = QtCore.Qt.CheckState.Checked if post_scan_set_val is not None else QtCore.Qt.CheckState.Unchecked
        self.scan_dev_post_scan_set_checkbox_clicked(ch_state, block_signal=True)
        if post_scan_set_val is not None:
            self.doubleSpinBox_scanDevPostScan.blockSignals(True)
            self.doubleSpinBox_scanDevPostScan.setValue(post_scan_set_val)
            self.doubleSpinBox_scanDevPostScan.blockSignals(False)

    def scan_dev_pre_val_copy_clicked(self, block_sig=True):
        """
        copy the current start value to the pre scan value
        will also update the doubleSpinbox
        """
        new_val = self.doubleSpinBox_scanDevStart.value()
        self.scan_dev_pre_scan_val_set(new_val, block_sig)
        self.doubleSpinBox_scanDevPreScan.blockSignals(block_sig)
        self.doubleSpinBox_scanDevPreScan.setValue(new_val)
        self.doubleSpinBox_scanDevPreScan.blockSignals(False)

    def scan_dev_post_val_copy_clicked(self, block_sig=True):
        """  copy the current start value to the post scan value """
        new_val = self.doubleSpinBox_scanDevStop.value()
        self.scan_dev_post_scan_val_set(new_val)
        self.doubleSpinBox_scanDevPostScan.blockSignals(block_sig)
        self.doubleSpinBox_scanDevPostScan.setValue(new_val)
        self.doubleSpinBox_scanDevPostScan.blockSignals(False)
        
    def scan_dev_pre_scan_set_checkbox_clicked(self, chbox_state, block_signal=True):
        """
        set the checkbox
        :param chbox_state:
        :return:
        """
        self.checkBox_scanDev_setPreScan.setChecked(chbox_state == QtCore.Qt.CheckState.Checked)
        self.doubleSpinBox_scanDevPreScan.setEnabled(chbox_state == QtCore.Qt.CheckState.Checked)
        self.pushButton_scanDev_pre_sc_copy_from_start.setEnabled(chbox_state == QtCore.Qt.CheckState.Checked)
        if chbox_state == QtCore.Qt.CheckState.Checked:
            new_val = self.buffer_pars['scanDevice'].get('preScanSetPoint', None)
            new_val = self.doubleSpinBox_scanDevStart.value() if new_val is None else new_val
            self.doubleSpinBox_scanDevPreScan.blockSignals(block_signal)
            self.doubleSpinBox_scanDevPreScan.setValue(new_val)
            self.doubleSpinBox_scanDevPreScan.blockSignals(False)
            self.buffer_pars['scanDevice']['preScanSetPoint'] = new_val
        else:
            self.buffer_pars['scanDevice']['preScanSetPoint'] = None
    
    def scan_dev_post_scan_set_checkbox_clicked(self, chbox_state, block_signal=True):
        """
        set the checkbox
        :param chbox_state:
        :return:
        """
        self.checkBox_scanDev_setPostScan.setChecked(chbox_state == QtCore.Qt.CheckState.Checked)
        self.doubleSpinBox_scanDevPostScan.setEnabled(chbox_state == QtCore.Qt.CheckState.Checked)
        self.pushButton_scanDev_post_ssc_copy_stop.setEnabled(chbox_state == QtCore.Qt.CheckState.Checked)
        if chbox_state == QtCore.Qt.CheckState.Checked:
            new_val = self.buffer_pars['scanDevice'].get('postScanSetPoint', None)
            new_val = self.doubleSpinBox_scanDevStop.value() if new_val is None else new_val
            self.doubleSpinBox_scanDevPostScan.blockSignals(block_signal)
            self.doubleSpinBox_scanDevPostScan.setValue(new_val)
            self.doubleSpinBox_scanDevPostScan.blockSignals(False)
            self.buffer_pars['scanDevice']['PostScanSetPoint'] = new_val
        else:
            self.buffer_pars['scanDevice']['PostScanSetPoint'] = None

    def calc_n_of_steps(self):
        """ calculates the number of steps: abs((stop - start) / stepSize) """
        try:
            start = self.check_for_none(self.buffer_pars['scanDevice'].get('start'), 0)
            stop = self.scan_dev_stop_by_user
            step_size = self.check_for_none(self.buffer_pars['scanDevice'].get('stepSize'), 1)
            try:
                dis = abs(stop - start) + abs(step_size)
                n_of_steps = dis / abs(step_size)
            except ZeroDivisionError:
                n_of_steps = 0
            if self._uses_internal_fpga_dac_quantization():
                # for DAC bitwise calc!
                start_18b = VCon.get_nbits_from_voltage(start)  # change to bits first
                stop_18b = VCon.get_nbits_from_voltage(stop)
                step_size_18b = VCon.get_nbit_stepsize(step_size)
                n_of_steps = VCon.calc_n_of_steps(start_18b, stop_18b, step_size_18b)
        except Exception as e:
            logging.error('following error occurred while calculating the number of steps:' + str(e))
            n_of_steps = 0
        return n_of_steps  # sign should always be in the stepsize

    def scan_dev_step_size_set(self, step_size):
        """ if the stepsize is set, adjust the number of steps to keep start and stop constant"""
        if self._uses_internal_fpga_dac_quantization():
            # for DAC bitwise calc!
            step_18bit = VCon.get_nbit_stepsize(step_size)
            step_size = VCon.get_stepsize_in_volt_from_bits(step_18bit)
        self.display_step_size(step_size)
        if not self.recalc_n_of_steps_stop():  # for invalid stop value, return to last valid value
            self.display_step_size(step_size)
            self.recalc_n_of_steps_stop()

    def display_step_size(self, step_size):
        """ stores the stepSize to the working dictionary and displays them """
        self.buffer_pars['scanDevice']['stepSize'] = step_size
        if self._uses_internal_fpga_dac_quantization():
            # for DAC bitwise calc!
            step_18bit = VCon.get_nbit_stepsize(step_size)
            step_size = VCon.get_stepsize_in_volt_from_bits(step_18bit)
            self.label_dacStepSizeV_set.setText(str(round(step_size, 8)) + ' | ' + str(step_18bit))
            self.label_kepco_step.setText(str(round(step_size * 50, 2)))
        else:
            self.label_dacStepSizeV_set.setText('%.8f' % step_size)
            self.label_kepco_step.setText('')
        self.doubleSpinBox_scanDevStepSize.blockSignals(True)
        self.doubleSpinBox_scanDevStepSize.setValue(step_size)
        self.doubleSpinBox_scanDevStepSize.blockSignals(False)

    def n_of_steps_set(self, steps):
        """ displays the number of steps that where set and recalculates the stepSize
         in order to keep start and stop more or less constant """
        self.display_n_of_steps(steps)
        self.display_step_size(self.calc_step_size())
        self.display_stop(self.calc_scan_dev_stop_val())

    def display_n_of_steps(self, steps):
        """ write the number of steps to the working dictionary and display them """
        steps = int(steps)
        self.label_nOfSteps_set.setText(str(steps))
        self.buffer_pars['nOfSteps'] = steps
        self.spinBox_nOfSteps.blockSignals(True)
        self.spinBox_nOfSteps.setValue(steps)
        self.spinBox_nOfSteps.blockSignals(False)

    '''other scan pars:'''

    def n_of_scans_set(self, val):
        """ write the number of scans to the working dictionary and display them """
        self.label_nOfScans_set.setText(str(val))
        self.buffer_pars['nOfScans'] = val

    def invert_scan_set(self, state):
        """ write to the working dictionary and set the label """
        if state:
            boolstate = True
        else:
            boolstate = False
        self.label_invertScan_set.setText(str(boolstate))
        self.buffer_pars['invertScan'] = boolstate

    def active_pmt_list_set(self, lis):
        """ write to the working dictionary and set the label """
        if type(lis) == str:
            try:
                lis = str('[' + lis + ']')
                lis = ast.literal_eval(lis)
            except Exception as e:
                logging.debug('while converting the pmt list, this occurred: ' + str(e))
                lis = []
        self.label_activePmtList_set.setText(str(lis))
        self.buffer_pars['activePmtList'] = lis

    def col_dir_true_set(self, state):
        """ write to the working dictionary and set the label """
        if state:
            display = 'collinear'
            boolstate = True
        else:
            display = 'anti-collinear'
            boolstate = False
        self.label_colDirTrue_set.setText(display)
        self.buffer_pars['colDirTrue'] = boolstate

    def wait_after_reset_mu_sec_set(self, time_mu_s):
        """ write to the working dictionary and set the label """
        time_us = int(time_mu_s)
        self.buffer_pars['waitAfterReset1us'] = time_us
        setval = time_us
        self.label_waitAfterReset_muS_set.setText(str(setval))

    def wait_for_kepco_mu_sec(self, time_mu_s):
        """ write to the working dictionary and set the label """
        time_1_us = int(time_mu_s)
        self.buffer_pars['waitForKepco1us'] = time_1_us
        setval = time_1_us
        self.label_waitForKepco_muS_set.setText(str(setval))

    """ set offset voltages (heinzingers) """

    def post_acc_offset_volt_control_set(self, index):
        """ write to the working dictionary and set the label """
        val = self.comboBox_postAccOffsetVoltControl.currentText()
        if val != 'Kepco':
            if Cfg._main_instance is not None:
                Cfg._main_instance.power_supply_status(val, self.subscription_name)
        self.label_postAccOffsetVoltControl_set.setText(val)
        self.buffer_pars['postAccOffsetVoltControl'] = index

    def refresh_pow_sup_readback(self, stat_dict):
        """
        refresh the readback voltage whenever the signal is triggered.
        """
        name = self.comboBox_postAccOffsetVoltControl.currentText()
        try:
            self.label_postAccOffsetVoltControl_set.setText(
                str(stat_dict.get(name, {}).get('readBackVolt', 'not initalized')))
        except Exception as e:
            logging.error('while reading the status, this happened: ' + str(e))

    def post_acc_offset_volt(self, val):
        """ write to the working dictionary and set the label """
        self.label_postAccOffsetVolt_set.setText(str(val))
        self.buffer_pars['postAccOffsetVolt'] = val

    def set_voltage(self):
        """ this will connect to the corresponding Heinzinger and set the voltage.
         this helps the user to enter the voltage a while before the scan."""
        power_supply = self.comboBox_postAccOffsetVoltControl.currentText()
        if power_supply != 'Kepco':
            volt = self.buffer_pars['postAccOffsetVolt']
            if Cfg._main_instance is not None:
                Cfg._main_instance.set_power_supply_voltage(power_supply, volt, self.subscription_name)
                self.set_volt_win = SetVoltageUi(power_supply, volt, self.subscription_name)

    """ other stuff """

    def cancel(self):
        """ closes the window without further actions """
        self.close()

    def confirm(self):
        """ closes the window and overwrites the corresponding track in the main """
        self._canonicalize_legacy_scan_device_labels(self.buffer_pars.get('scanDevice', {}))
        start = self.buffer_pars['scanDevice']['start']
        stop = self.buffer_pars['scanDevice']['stop']
        self.buffer_pars = SdOp.merge_dicts(self.buffer_pars, self.sequencer_widget.get_seq_pars(start, stop))
        self.buffer_pars['trigger'] = {'meas_trigger': self.trigger_widget.get_trig_pars(),
                                       'step_trigger': self.step_trigger_widget.get_trig_pars(),
                                       'scan_trigger': self.scan_trigger_widget.get_trig_pars()}
        if Cfg._main_instance is not None:
            Cfg._main_instance.scan_pars[self.active_iso][self.track_name] = deepcopy(self.buffer_pars)
        logging.debug('confirmed track dict: ' + str(self.buffer_pars))
        # logging.debug('measure volt pars:')
        # import json
        # logging.debug(
        #     json.dumps(self.buffer_pars['measureVoltPars'], sort_keys=True, indent=4))
        self.close()

    def enable_confirm(self, enable_bool):
        """ when the current isotope is scanning, it should not be possible to make changes to its tracks """
        self.pushButton_confirm.setEnabled(enable_bool)
        if not enable_bool:
            self.pushButton_confirm.setToolTip('Scanning now!')

    def reset_to_default(self):
        """ will reset all spinboxes to the default value which is stored in the main. """
        if Cfg._main_instance is not None:
            default_d = deepcopy(Cfg._main_instance.scan_pars[self.active_iso][self.track_name])
        else:
            default_d = deepcopy(dft.draftTrackPars)
        default_d['stop'] = self.calc_scan_dev_stop_val()
        self.set_labels_by_dict(default_d)

    def closeEvent(self, event):
        """
        will remove the given track window from the dictionary in scan_ctrl_win
        """
        if Cfg._main_instance is not None:
            Cfg._main_instance.un_subscribe_to_power_sub_status(self.subscription_name)
        if self.scan_ctrl_win is not None:
            self.scan_ctrl_win.track_win_closed(self.track_number)
        if self.pulse_pattern_win is not None:
            self.pulse_pattern_win.close()
        if self.pre_post_scan_window is not None:
            self.pre_post_scan_window.close()
        if self.outbit_win is not None:
            self.outbit_win.close()
        if self._scan_main_for_debugging is not None:
            self._scan_main_for_debugging.close_scan_main()

    def raise_win_to_front(self, window):
        # this will remove minimized status
        # and restore window with keeping maximized/normal state
        window.setWindowState(
            window.windowState() & ~QtCore.Qt.WindowState.WindowMinimized | QtCore.Qt.WindowState.WindowActive)

        # this will activate the window
        window.activateWindow()


if __name__ == '__main__':
    import sys

    log_formatter = logging.Formatter('%(asctime)s %(levelname)s %(module)s %(funcName)s(%(lineno)d) %(message)s')

    app_log = logging.getLogger()
    app_log.setLevel(logging.DEBUG)
    app_log.info('Log level set to ' + 'DEBUG')
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    # ch.setFormatter(log_formatter)
    app_log.addHandler(ch)

    app_log.info('****************************** starting ******************************')
    app_log.info('Log level set to DEBUG')

    app = QtWidgets.QApplication(sys.argv)
    gui = TrackUi(None, 0, 'lala', None)
    # gui.load_from_text(txt_path='E:\\TildaDebugging\\Pulsepattern123Pattern.txt')
    # print(gui.get_gr_v_pos_from_list_of_cmds())
    app.exec_()

