"""

Created on '19.05.2015'

@author:'simkaufm'

"""
import ctypes
import datetime
import logging
from copy import deepcopy
from enum import Enum, unique
from os import path, pardir

import numpy as np


@unique
class Ni4071TriggerSources(Enum):
    """
    Immediate (1) No trigger specified
    Interval (10) Interval trigger
    External (2) Pin 9 on the AUX Connector
    Software Trig (3) Configures the DMM to wait until niDMM Send Software Trigger is called.
    TTL 0 (111) PXI Trigger Line 0
    TTL 1 (112) PXI Trigger Line 1
    TTL 2 (113) PXI Trigger Line 2
    TTL 3 (114) PXI Trigger Line 3
    TTL 4 (115) PXI Trigger Line 4
    TTL 5 (116) PXI Trigger Line 5
    TTL 6 (117) PXI Trigger Line 6
    TTL 7 (118) PXI Trigger Line 7
    PXI Star (131) PXI Star trigger line
    LBR Trig 1 (1004) Local Bus Right Trigger Line 1 of PXI/SCXI combination chassis
    AUX Trig 1 (1001) Pin 3 on the AUX connector
    """
    immediate = 1
    interval = 10
    external = 2
    softw_trig = 3
    pxi_trig_0 = 111
    pxi_trig_1 = 112
    pxi_trig_2 = 113
    pxi_trig_3 = 114
    pxi_trig_4 = 115
    pxi_trig_5 = 116
    pxi_trig_6 = 117
    pxi_trig_7 = 118
    pxi_star_trig = 131
    lbr_trig_1 = 1004
    auf_trig_1 = 1001


@unique
class Ni4071MeasCompleteLoc(Enum):
    """
    Specifies the destination of the DMM Measurement Complete (MC) signal.
    :param meas_compl_dest: int, This signal is issued when the DMM completes a single measurement.
     This signal is commonly referred to as Voltmeter Complete.

    None (-1) No destination specified.
    External (2) Pin 6 on the AUX Connector
    TTL 0 (111) PXI Trigger Line 0
    TTL 1 (112) PXI Trigger Line 1
    TL 2 (113) PXI Trigger Line 2
    TTL 3 (114) PXI Trigger Line 3
    TL 4 (115) PXI Trigger Line 4
    TTL 5 (116) PXI Trigger Line 5
    TTL 6 (117) PXI Trigger Line 6
    TTL 7 (118) PXI Trigger Line 7
    LBR Trig 0 (1003) Local Bus Right Trigger Line 0 of PXI/SCXI combination chassis
    """
    undefined = -1
    external = 2
    PXI_Trigger_0 = 111
    PXI_Trigger_1 = 112
    PXI_Trigger_2 = 113
    PXI_Trigger_3 = 114
    PXI_Trigger_4 = 115
    PXI_Trigger_5 = 116
    PXI_Trigger_6 = 117
    PXI_Trigger_7 = 118
    lbr_trig_0 = 1003
    software = 0


class Ni4071PreConfigs(Enum):
    initial = {
        'range': '1000.0',
        'resolution': '7.5',
        'nplc': '10',
        'triggerCount': 5,
        'sampleCount': 5,
        'autoZero': -1,
        'triggerSource': 'pxi_trig_3',
        'sampleInterval': -1,
        'powerLineFrequency': '50.0',
        'triggerDelay_s': 0,
        'triggerSlope': 'rising',
        'measurementCompleteDestination': Ni4071MeasCompleteLoc.PXI_Trigger_4.name,
        'highInputResistanceTrue': False,
        'assignment': 'offset',
        'accuracy': (None, None),
        'preConfName': 'initial'
    }
    periodic = {
        'range': '1000.0',
        'resolution': '7.5',
        'nplc': '10',
        'triggerCount': 0,
        'sampleCount': 0,
        'autoZero': -1,
        'triggerSource': Ni4071TriggerSources.immediate.name,
        'sampleInterval': -1,
        'powerLineFrequency': '50.0',
        'triggerDelay_s': 0,
        'triggerSlope': 'rising',
        'measurementCompleteDestination': Ni4071MeasCompleteLoc.PXI_Trigger_4.name,
        'highInputResistanceTrue': False,
        'accuracy': (None, None),
        'assignment': 'offset',
        'preConfName': 'periodic'
    }
    pre_scan = {
        'range': '1000.0',
        'resolution': '7.5',
        'nplc': '100',
        'triggerCount': 0,
        'sampleCount': 1,
        'autoZero': -1,
        'triggerSource': Ni4071TriggerSources.softw_trig.name,
        'sampleInterval': -1,
        'powerLineFrequency': '50.0',
        'triggerDelay_s': 0,
        'triggerSlope': 'rising',
        'measurementCompleteDestination': Ni4071MeasCompleteLoc.PXI_Trigger_4.name,
        'highInputResistanceTrue': False,
        'accuracy': (None, None),
        'assignment': 'offset',
        'preConfName': 'pre_scan'
    }
    kepco = {
        'range': '1000.0',
        'resolution': '7.5',
        'nplc': '100',
        'triggerCount': 0,
        'sampleCount': 0,
        'autoZero': -1,
        'triggerSource': Ni4071TriggerSources.pxi_trig_3.name,
        'sampleInterval': -1,
        'powerLineFrequency': '60.0',
        'triggerDelay_s': 0.05,
        'triggerSlope': 'rising',
        'measurementCompleteDestination': Ni4071MeasCompleteLoc.PXI_Trigger_4.name,
        'highInputResistanceTrue': False,
        'accuracy': (None, None),
        'assignment': 'offset',
        'preConfName': 'kepco'
    }


class Ni4071:
    """
    Class for accessing the National Instruments 4071 digital Multimeter.
    """

    def __init__(self, reset=True, address_str='PXI1Slot5', pwr_line_freq='50.0'):
        dll_path = path.join(path.dirname(__file__), pardir, pardir, pardir, 'Tilda\\binary\\nidmm_64.dll')

        self.type = 'Ni4071'
        self.state = 'None'
        self.address = address_str
        self.name = self.type + '_' + address_str
        # default config dictionary for this type of DMM:

        self.pre_configs = Ni4071PreConfigs
        self.selected_pre_config_name = self.pre_configs.periodic.name
        self.config_dict = self.pre_configs.periodic.value
        self.get_accuracy()

        self.last_readback = None  # tuple, (voltage_float, time_str)
        self.dll = ctypes.WinDLL(dll_path)
        self.session = ctypes.c_uint32(0)

        stat = self.init(address_str, reset_dev=reset)
        if stat < 0:  # if init fails, start simulation
            self.get_error_message(stat, 'while initializing Ni4071: ')
            self.de_init_dmm()
            logging.warning('initialisation of %s did not work, starting simulation now' % self.name)
            stat = self.init_with_option(address_str, "Simulate=1, DriverSetup=Model:4071; BoardType:PXI")
            self.get_error_message(stat)
        self.config_power_line_freq(pwr_line_freq)

        logging.info('%s initialized, status is: %s, session is: %s' % (self.name, stat, self.session))

    ''' Init and close '''

    def init(self, dev_name, id_query=True, reset_dev=True):
        """
        Creates a new session to the instrument
        :return: the status
        """
        dev_name = ctypes.create_string_buffer(dev_name.encode('utf-8'))
        ret = self.dll.niDMM_init(dev_name, id_query, reset_dev, ctypes.byref(self.session))
        if ret >= 0:
            self.state = 'initialized'
        else:
            self.state = 'error %s %s' % (self.get_error_message(ret, comment=''))
        return ret

    def init_with_option(self, dev_name, options_string, id_query=True, reset_dev=True):
        """
        initialize the dmm with options.
        e.g. "Simulate=1, DriverSetup=Model:4071; BoardType:PXI" to simulate a pxi device
        :param dev_name: str, resource name of the dev
        :param options_string: str, can be used to pass the options
        :param id_query: bool
        :param reset_dev: bool
        :return: the status
        """
        dev_name = ctypes.create_string_buffer(dev_name.encode('utf-8'))
        options_string = ctypes.create_string_buffer(options_string.encode('utf-8'))
        ret = self.dll.niDMM_InitWithOptions(
            dev_name, id_query, reset_dev, options_string, ctypes.byref(self.session))
        if ret > 0:
            self.state = 'initialized'
        else:
            self.state = 'error %s %s' % (self.get_error_message(ret, comment=''))
        return ret

    def de_init_dmm(self):
        ''' Closes the current session to the instrument. '''
        if self.readstatus()[1] != 4:
            self.abort_meas()
        self.dll.niDMM_close(self.session)
        self.session = ctypes.c_ulong(0)

    ''' Configure '''

    def config_measurement(self, dmm_range, resolution, func=1):
        """
        Configures the common properties of the measurement.
        named configure measurement digits in quick ref.
        :param dmm_range: str, range 10.00, 100.00, etc.
        valid ranges: 0.1, 1.0, 10.0, 100.0, 1000.0
        Auto range ON: -1.0
        Auto range OFF: -2.0
        Auto range ONCE: -3.0
        :param resolution: str, resolution in digits
        3.5 (3.5000000E+0) Specifies 3.5 digits resolution.
        4.5 (4.500000E+0) Specifies 4.5 digits resolution.
        5.5 (5.500000E+0) Specifies 5.5 digits resolution.
        6.5 (6.500000E+0) Specifies 6.5 digits resolution.
        7.5 (7.500000E+0) Specifies 7.5 digits resolution.
        :param func: int, DC volts, AC volts and so on
        1: DC Volts
        2: AC Volts
        3: DC Current
        4: AC Current
        5: 2 Wire Res
        101: 4 Wire Res
        106: AC Plus DC Volts
        107: AC Plus DC Current
        104: Freq
        105: period
        108: temperature
        """
        if isinstance(dmm_range, float):
            dmm_range = '%.1f' % dmm_range
        self.config_dict['range'] = deepcopy(dmm_range)
        if isinstance(resolution, float):
            resolution = '%.1f' % resolution
        self.config_dict['resolution'] = deepcopy(resolution)
        func = ctypes.c_int32(func)
        dmm_range = ctypes.c_double(float(dmm_range))
        res = ctypes.c_double(float(resolution))
        self.dll.niDMM_ConfigureMeasurementDigits(self.session, func, dmm_range, res)

    def config_multi_point_meas(self, trig_count, sample_count, trig_src_enum, sample_interval):
        """
        Configures the properties for multipoint measurements.
        :param trig_count: int, nuzmber of triggers before returning to idle state
        :param sample_count: int32, sets the number of measurements the DMM makes
         in each measurement sequence initiated by a trigger.

        :param trig_src_enum: enum, specifies the sample trigger source to use.
         Enum defined in Ni4071TriggerSources class

        :param sample_interval: dbl, sets the amount of time in seconds the DMM waits between measurement cycles.
        Specify a sample interval to add settling time
        between measurement cycles or to decrease the measurement rate. Sample Interval only applies
        when the Sample Trigger is set to Interval. On the NI 4060, the Sample Interval value
        is used as the settling time. When sample interval is set to 0, the DMM does not settle
        between measurement cycles. The NI 4065 and NI 4070/4071/4072 use the value specified in
        Sample Interval as additional delay. The default value (-1) ensures that the DMM settles
        for a recommended time. This is the same as using an Immediate trigger.
        """
        self.config_dict['triggerCount'] = trig_count
        self.config_dict['sampleCount'] = sample_count
        self.config_dict['triggerSource'] = trig_src_enum.name
        self.config_dict['sampleInterval'] = sample_interval
        trig_count = ctypes.c_int32(trig_count)
        sample_count = ctypes.c_int32(sample_count)
        sample_trig = ctypes.c_int32(trig_src_enum.value)
        sample_interval = ctypes.c_double(sample_interval)
        self.dll.niDMM_ConfigureMultiPoint(self.session, trig_count, sample_count, sample_trig, sample_interval)

    def conf_waveform_meas(self, func, wfm_range, rate, points):
        """
        Configures the NI 4070/4071/4072 for waveform acquisitions.
        :param func: int,
        WAVEFORM VOLTAGE (default) (1003) Waveform Voltage
        WAVEFORM CURRENT (1004) Waveform Current
        :param wfm_range: dbl,
        :param rate: dbl, specifies the rate of the acquisition in samples per second.
        The valid rate is 10.0 – 1,800,000 S/s. Values are coerced to the closest integer
        divisor of 1,800,000. The default value is 1,800,000.
        :param points: int, waveform points
        """
        func = ctypes.c_int32(func)
        wfm_range = ctypes.c_double(wfm_range)
        rate = ctypes.c_double(rate)
        points = ctypes.c_int32(points)
        self.dll.niDMM_ConfigureWaveformAcquisition(self.session, func, wfm_range, rate, points)

    ''' Measurement Options '''

    def config_power_line_freq(self, pwr_line_freq):
        """
        Specifies the powerline frequency.
        :param pwr_line_freq: dbl, 50 or 60 Hz
        """
        if isinstance(pwr_line_freq, float):
            pwr_line_freq = '%.1f' % pwr_line_freq
        self.config_dict['powerLineFrequency'] = deepcopy(pwr_line_freq)
        self.dll.niDMM_ConfigurePowerLineFrequency(self.session, ctypes.c_double(float(pwr_line_freq)))

    def config_auto_zero(self, auto_zero_mode):
        """
        Configures the DMM for Auto Zero. When Auto Zero is ON, the DMM internally disconnects the input
         and takes a zero reading. It then subtracts the zero reading from the measurement.
          This prevents offset voltages present on the input circuitry of the DMM from affecting
           measurement accuracy. When Auto Zero is OFF, the DMM does not compensate for zero reading offset.
        :param auto_zero_mode: int,
        Auto (default) (-1)  NI-DMM chooses the Auto Zero setting based on the configured function and resolution.
        Off (0) Disables Auto Zero.  Note  The NI 4065 does not support this setting.
        On (1) The DMM internally disconnects the input signal following each measurement and takes a zero reading.
            It then subtracts the zero reading from the preceding reading.
        Once (2) The DMM internally disconnects the input signal following each measurement and takes a zero reading.
            It then subtracts the zero reading from the preceding reading.
        """
        self.config_dict['autoZero'] = auto_zero_mode
        self.dll.niDMM_ConfigureAutoZeroMode(self.session, ctypes.c_int32(auto_zero_mode))

    def config_adc_cal(self, adc_cal_mode):
        """
        Allows the DMM to compensate for gain drift since the last external or self-calibration.
         When ADC Calibration is ON, the DMM measures an internal reference to calculate the correct gain
          for the measurement. When ADC Calibration is OFF, the DMM does not compensate for changes to the gain.
        :param adc_cal_mode: int,
        ON (-1) The DMM measures an internal reference to calculate the correct gain for the measurement.
        OFF (0) The DMM does not compensate for changes to the gain.
        AUTO (1) The DMM enables or disables ADC calibration based on the configured function and resolution.
        """
        self.dll.niDMM_ConfigureADCCalibration(self.session, ctypes.c_int32(adc_cal_mode))

    def config_offset_comp_ohms(self, off_comp_mode):
        """ Allows the DMM to compensate for voltage offsets in resistance measurements.
         When Offset Compensated Ohms is enabled, the DMM measures the resistance twice
          (once with the current source on and again with it turned off).
           Any voltage offset present in both measurements is cancelled out.
            Offset Compensated Ohms is useful when measuring resistance values less than 10 kOhms.
        OFF: 0
        ON: 1
        """
        self.dll.niDMM_ConfigureOffsetCompOhms(self.session, ctypes.c_int32(off_comp_mode))

    def config_ac_bandwith(self, min_freq, max_freq):
        """
        Configures the Min Frequency and Max Frequency properties that the DMM uses for AC measurements.
        :param min_freq: dbl, Minimum Frequency   Hz
        :param max_freq: dbl, Maximum Freq. Hz
        """
        self.dll.niDMM_ConfigureACBandwidth(self.session, ctypes.c_double(min_freq), ctypes.c_double(max_freq))

    def config_freq_volt_range(self, freq_volt):
        """
         Specifies the expected maximum amplitude of the input signal for frequency and period measurements.
        :param freq_volt: dbl,
        ranges: 0.1, 1.0, 10.0, 100.0, 1000.0 V
        or
        Auto Range ON: -1.0
        Auto Range OFF: -2.0
        """
        self.dll.niDMM_ConfigureFrequencyVoltageRange(self.session, ctypes.c_double(freq_volt))

    def config_current_source(self, src):
        """
        Configures the current source for diode measurements. The NI 4050 and NI 4060 are not supported.
        :param src: dbl, specifies the current source provided during diode measurements.
        valid values: 0.000001, 0.000010, 0.000100, 0.001000 A
        ranges: Diode 10 V at 1 µA / 10µA / 100µA; 4.0 V at 1 mA
        """
        self.dll.niDMM_ConfigureCurrentSource(self.session, ctypes.c_double(src))

    def config_wavefrom_coupling(self, coupling):
        """
        Configures instrument coupling for voltage waveforms.
        :param coupling: int, selects DC or AC coupling
        AC coupling: 0
        DC coupling: 1 (default)
        """
        self.dll.niDMM_ConfigureWaveformCoupling(self.session, ctypes.c_int32(coupling))

    ''' Triggers '''

    def config_trigger(self, trig_src_enum, trig_delay):
        """
        Configures the DMM trigger source and trigger delay.
        :param trig_src_enum: enum, specifies the sample trigger source to use.
         Enum defined in Ni4071TriggerSources class.

        :param trig_delay: dbl, NI-DMM sets the Trigger Delay property to this value.
        By default, Trigger Delay is -1, which means the DMM waits an appropriate settling time
        before taking the measurement. The NI 4065 and NI 4070/4071/4072 use the value
        specified in Trigger Delay as ADDITIONAL settling time.

        valid values:
        0.0 to 149.0 s (resolution is 0.1 s)
        -1.0: auto delay ON
        -2.0: auto delay OFF
        """
        self.config_dict['triggerSource'] = trig_src_enum.name
        self.config_dict['triggerDelay_s'] = trig_delay
        self.dll.niDMM_ConfigureTrigger(
            self.session, ctypes.c_int32(trig_src_enum.value), ctypes.c_double(trig_delay))

    def send_software_trigger(self):
        """
        sends a command to trigger the DMM
        """
        self.dll.niDMM_SendSoftwareTrigger(self.session)

    def config_trigger_slope(self, trig_slope):
        """
        Sets the Trigger Slope property to either rising edge (positive) or falling edge (negative) polarity.
        :param trig_slope: int,
        Rising Edge: 0
        Falling Edge: 1 (default)
        """
        self.config_dict['triggerSlope'] = 'falling' if trig_slope else 'rising'
        self.dll.niDMM_ConfigureTriggerSlope(self.session, ctypes.c_int32(trig_slope))

    def config_sample_trigger_slope(self, smpl_trig_slope):
        """
        Sets the Sample Trigger Slope property to either rising edge (positive) or falling edge (negative) polarity.
        (For multipoint acquisition)
        :param smpl_trig_slope: int,
        Rising Edge: 0
        Falling Edge: 1 (default)
        """
        self.config_dict['triggerSlope'] = 'falling' if smpl_trig_slope else 'rising'
        self.dll.niDMM_ConfigureSampleTriggerSlope(self.session, ctypes.c_int32(smpl_trig_slope))

    def config_meas_complete_dest(self, meas_compl_dest_enum):
        """
        Specifies the destination of the DMM Measurement Complete (MC) signal.
        :param meas_compl_dest: enum, as defined in Ni4071MeasCompleteLoc class.
        """
        self.config_dict['measurementCompleteDestination'] = meas_compl_dest_enum.name
        if meas_compl_dest_enum != Ni4071MeasCompleteLoc.software:
            self.dll.niDMM_ConfigureMeasCompleteDest(self.session, ctypes.c_int32(meas_compl_dest_enum.value))

    def config_meas_complete_slope(self, meas_compl_slope):
        """
        Sets the Measurement Complete signal to either rising edge (positive) or falling edge (negative) polarity.
        :param meas_compl_slope: int,
        Rising Edge: 0
        Falling Edge: 1 (default)
        """
        self.dll.niDMM_ConfigureMeasCompleteSlope(self.session, ctypes.c_int32(meas_compl_slope))

    ''' Actual Values '''

    def get_auto_range_value(self):
        """
        Returns the actual range that the DMM is using, even when auto ranging is off.
        :return: dbl, auto range value
        """
        ret_val = ctypes.c_double()
        self.dll.niDMM_GetAutoRangeValue(self.session, ctypes.byref(ret_val))
        return ret_val.value

    def get_aperture_time_info(self):
        """
        Returns the aperture time and aperture time units.
        specifies the amount of time the DMM digitizes the input signal for a single measurement.
        This parameter does not include settling time.
        On the NI 4070/4071/4072, the minimum aperture time is 8.89 µs, and the maximum aperture time is 149 s.
        Any number of powerline cycles (PLCs) within the minimum and maximum ranges
        is allowed on the NI 4070/4071/4072.
        :return: (dbl, str), (aperture time, unit)
        """
        apt_t = ctypes.c_double()
        apt_u = ctypes.c_int32()
        self.get_error_message(
            self.dll.niDMM_GetApertureTimeInfo(self.session, ctypes.byref(apt_t), ctypes.byref(apt_u)))
        units = 'seconds'
        if apt_u.value:
            units = 'power line cycles'
        return apt_t.value, units

    def get_meas_period(self):
        """
        Returns the Measurement Period, which is the amount of time it takes to complete
        one measurement with the current configuration.
        :return: dbl, returns the number of seconds it takes to make one measurement.
        The first measurement in a multipoint acquisition requires additional settling time.
        """
        meas_per = ctypes.c_double()
        self.dll.niDMM_GetMeasurementPeriod(self.session, ctypes.byref(meas_per))
        return meas_per.value

    ''' Acquisition '''

    def read_single_voltage(self, max_time_ms=-1):
        """
        Acquires a single measurement and returns the measured value.
        :param max_time_ms: int, specifies the maximum time allowed for this VI to complete in milliseconds.
        If the VI does not complete within this time interval, the VI returns the
        NIDMM_ERROR_MAX_TIME_EXCEEDED error code. This may happen if an external trigger has not been received,
        or if the specified timeout is not long enough for the acquisition to complete.
        The valid range is 0–86400000.
        The default value is TIME LIMIT AUTO (-1). The DMM calculates the timeout automatically.
        :return: dbl, voltage
        """
        max_time_ms = ctypes.c_int32(max_time_ms)
        read = ctypes.c_double()
        self.dll.niDMM_Read(self.session, max_time_ms, ctypes.byref(read))
        return read.value

    def read_multi_point(self, number_to_read, max_time=-1):
        """
        Acquires multiple measurements and returns an array of measured values.
        The number of measurements the DMM makes is determined by the values you specify
        for the Trigger Count and Sample Count parameters of niDMM Configure Multi Point.
        :param max_time: int, specifies the maximum time allowed for this VI to complete in milliseconds.
         0-86400000 allowed.
         -1 means Auto
        :param number_to_read: specifies the number of measurements to acquire.
        The maximum number of measurements for a finite acquisition is the (Trigger Count x Sample Count)
        parameters in niDMM Configure Multi Point.
        For continuous acquisitions, up to 100,000 points can be returned at once.
        The number of measurements can be a subset.
        The valid range is any positive ViInt32. The default value is 1.
        :return: numpy array with all values
        """
        max_time = ctypes.c_int32(max_time)
        array_of_values = ctypes.c_double * number_to_read
        array_of_values = array_of_values()
        number_to_read = ctypes.c_int32(number_to_read)
        number_of_read_elements = ctypes.c_int32()
        self.dll.niDMM_ReadMultiPoint(
            self.session, max_time, number_to_read, array_of_values, ctypes.byref(number_of_read_elements))
        return np.ctypeslib.as_array(array_of_values)[0:number_of_read_elements.value]

    def read_waveform(self, max_time=-1, num_to_read=1):
        """
        Acquires a waveform and returns data as an array of values or as a waveform data type.
        :param max_time: int, specifies the maximum time allowed for this VI to complete in milliseconds.
         0-86400000 allowed.
         -1 means Auto
        :param num_to_read: int, specifies the number of waveform points to return.
        :return: numpy array with all values
        """
        max_time = ctypes.c_int32(max_time)
        array_of_values = ctypes.c_double * num_to_read
        array_of_values = array_of_values()
        number_to_read = ctypes.c_int32(num_to_read)
        number_of_read_elements = ctypes.c_int32()
        self.dll.niDMM_ReadWaveform(
            self.session, max_time, number_to_read, array_of_values, ctypes.byref(number_of_read_elements))
        return np.ctypeslib.as_array(array_of_values)[0:number_of_read_elements.value]

    def check_over_range(self, measurement):
        """
        Takes a measurement value and determines if the value is a valid measurement
         or a value indicating that an overrange condition occurred.
        :param measurement: dbl, is the measured value returned from the DMM.
        Note  If an overrange condition occurs, the Measurement value
        contains an IEEE-defined NaN (Not a Number) value.
        :return: bool, True if overrange
        """
        ret_bool = ctypes.c_bool()
        self.dll.niDMM_IsOverRange(self.session, ctypes.c_double(measurement), ctypes.byref(ret_bool))
        return ret_bool.value

    ''' low-level Acquisition '''

    def initiate_measurement(self):
        """
        Initiates an acquisition.
         After you call this VI, the DMM leaves the Idle state and enters the Wait-For-Trigger state.
          If trigger is set to Immediate mode, the DMM begins acquiring measurement data.
          Use fetch_single_meas(), niDMM Fetch Multi Point, or niDMM Fetch Waveform to retrieve the measurement data.
        """
        self.get_error_message(self.dll.niDMM_Initiate(self.session))
        tries = 0
        max_tries = 10
        while self.readstatus()[1] != 0 and tries <= max_tries:
            tries += 1
        if self.readstatus()[1] == 0:
            logging.debug('successfully started measurement on Ni4071 after %s tries' % tries)
        else:
            logging.error('error: could not started measurement on Ni4071 after %s tries' % tries)
            logging.error('error: status of Ni4071 is: backlog: %s acquisition state: %s' % self.readstatus())
        self.state = 'measuring'

    def fetch_single_meas(self, max_time_ms=-1):
        """
        Returns the value from a previously initiated measurement.
        You must call initiate_measurement() before calling this function.
        :param max_time_ms: int, specifies the maximum time allowed for this VI to complete in milliseconds.
         0-86400000 allowed.
         -1 means Auto
        :return: dbl, measurement value
        """
        max_time_ms = ctypes.c_int32(max_time_ms)
        read = ctypes.c_double()
        self.dll.niDMM_Fetch(self.session, max_time_ms, ctypes.byref(read))
        return read.value

    def fetch_multiple_meas(self, num_to_read=4, max_time_ms=5):
        """
        Returns an array of values from a previously initiated multipoint measurement.
        The number of measurements the DMM makes is determined by the values you specify
        for the Trigger Count and Sample Count parameters of niDMM Configure Multi Point.
        You must call initiate_measurement() to initiate a measurement before calling this function
        :param max_time_ms: int, specifies the maximum time allowed for this VI to complete in milliseconds.
         0-86400000 allowed.
         -1 means Auto
        :param num_to_read: int, specifies the number of measurements to acquire.
        The maximum number of measurements for a finite acquisition is the (Trigger Count x Sample Count)
        parameters in config_multi_point_meas()
        For continuous acquisitions, up to 100,000 points can be returned at once.
        num_to_read = -1 will read all available data
        :return: numpy array with all values
        """
        max_time = ctypes.c_int32(max_time_ms)
        if num_to_read < 0:  # read all available
            num_to_read = self.readstatus()[0]
        if num_to_read == 0:
            return np.zeros(0, dtype=np.double)
        array_of_values = ctypes.c_double * num_to_read
        array_of_values = array_of_values()
        number_to_read = ctypes.c_int32(num_to_read)
        number_of_read_elements = ctypes.c_int32()
        self.dll.niDMM_FetchMultiPoint(
            self.session, max_time, number_to_read, array_of_values, ctypes.byref(number_of_read_elements))
        ret = np.ctypeslib.as_array(array_of_values)[0:number_of_read_elements.value]
        if ret.any():
            t = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # take last element out of array and make a tuple with timestamp:
            self.last_readback = (round(ret[-1], 8), t)
        return ret

    def fetch_waveform(self, max_time_ms=-1, num_to_read=1):
        """
        Returns an array of values from a previously initiated multipoint measurement.
        The number of measurements the DMM makes is determined by the values you specify
        for the Trigger Count and Sample Count parameters of niDMM Configure Multi Point.
        You must call initiate_measurement() to initiate a measurement before calling this function
        :param max_time_ms: int, specifies the maximum time allowed for this VI to complete in milliseconds.
         0-86400000 allowed.
         -1 means Auto
        :param num_to_read: int, specifies the number of measurements to acquire.
        The maximum number of measurements for a finite acquisition is the (Trigger Count x Sample Count)
        parameters in config_multi_point_meas()
        For continuous acquisitions, up to 100,000 points can be returned at once.
        :return: numpy array with all values
        """
        max_time = ctypes.c_int32(max_time_ms)
        array_of_values = ctypes.c_double * num_to_read
        array_of_values = array_of_values()
        number_to_read = ctypes.c_int32(num_to_read)
        number_of_read_elements = ctypes.c_int32()
        self.dll.niDMM_FetchWaveform(
            self.session, max_time, number_to_read, array_of_values, ctypes.byref(number_of_read_elements))
        return np.ctypeslib.as_array(array_of_values)[0:number_of_read_elements.value]

    def readstatus(self):
        """
        Returns measurement backlog and acquisition status.
        :return: (backlog, acqusition_state)
          * Backlog specifies the number of measurements available to be read.
           If the backlog continues to increase, data is eventually overwritten, resulting in an error.
          * Acquisition State indicates status of the acquisition.
                0 Running
                1 Finished with Backlog
                2 Finished with no Backlog
                3 Paused
                4 No acquisition in progress
        """
        ret_backlog = ctypes.c_int32()
        ret_acqstate = ctypes.c_int16()
        self.dll.niDMM_ReadStatus(self.session, ctypes.byref(ret_backlog), ctypes.byref(ret_acqstate))
        return ret_backlog.value, ret_acqstate.value

    def abort_meas(self):
        """
        Aborts a previously initiated measurement and returns the DMM to the Idle state.
        """
        self.dll.niDMM_Abort(self.session)
        self.state = 'aborted'

    ''' Utility '''

    def reset_dev(self):
        """
        Resets the instrument to a known state and sends initialization commands to the instrument.
        The initialization commands set instrument settings to the state
        necessary for the operation of the instrument driver.
        :return:
        """
        logging.debug('Resetting DMM: ' + self.name)
        self.dll.niDMM_reset(self.session)

    def self_test(self):
        """
        Performs a self test on the DMM to ensure that the DMM is functioning properly.
        Self test does not calibrate the DMM.
        This function calls reset_dev(), and any configurations previous to the call will be lost.
        All properties will be set to their default values after the call returns.
        :return: (int, str), (test_res_num, test_res_message):
            * test_res_num, contains the value returned from the instrument self test. Zero indicates success.
            * For the NI 4065 and NI 4070/4071/4072, the error code returned for a self-test failure
             is NIDMM_ERROR_SELF_TEST_FAILURE. This error code indicates that the DMM should be repaired.
        """
        test_res = ctypes.c_int16()
        test_message = ctypes.create_string_buffer("".encode('utf-8'), 256)
        self.dll.niDMM_self_test(self.session, ctypes.byref(test_res), test_message)
        return test_res.value, test_message.value.decode('utf-8')

    def revision_query(self):
        """
        Returns the revision numbers of the instrument driver and instrument firmware.
        :return: (str, str), (instr. driver rev, firmware rev.)
        """
        instr_driver_rev = ctypes.create_string_buffer("".encode('utf-8'), 256)
        firmware_rev = ctypes.create_string_buffer("".encode('utf-8'), 256)
        self.dll.niDMM_revision_query(self.session, instr_driver_rev, firmware_rev)
        return instr_driver_rev.value.decode('utf-8'), firmware_rev.value.decode('utf-8')

    def get_digits_of_precision(self):
        """
        Returns the digits of precision calculated from the range and resolution information
        specified in config_meas_digits()
        :return: dbl, digits
        """
        ret_digits = ctypes.c_double()
        self.dll.niDMM_GetDigitsOfPrecision(self.session, ctypes.byref(ret_digits))
        return ret_digits.value

    def get_error_message(self, input, comment='Ni4071 yields error:'):
        """
        Takes the error cluster returned by the VIs, interprets it, and returns it as a user-readable string.
        :return: int, str
        """
        ret_status = ctypes.c_int32(input)
        ret_message = ctypes.create_string_buffer("".encode('utf-8'), 256)
        self.dll.niDMM_error_message(self.session, ret_status, ret_message)
        if ret_status.value < 0:
            logging.error(
                comment + ' errorcode is: ' + str(ret_status.value) +
                '\n error message is: ' + ret_message.value.decode('utf-8'))
        return ret_status.value, ret_message.value.decode('utf-8')

    ''' Calibration '''

    def self_calibration(self):
        """
        Executes the self-calibration routine to maintain measurement accuracy.

        Note  This VI calls niDMM Reset, and any configurations previous to the call will be lost.
        All properties will be set to their default values after the call returns.
        """
        self.dll.niDMM_SelfCal(self.session)

    def get_calibration_count(self, internal=True):
        """
        Returns the calibration count for the specified type of calibration.
        :param internal: bool, True for internal, False for external
        :return: int, number of calbrations of that type.
        """
        cal_type = ctypes.c_int32(1)
        if internal:
            cal_type = ctypes.c_int32(0)
        cal_count = ctypes.c_int32()
        self.dll.niDMM_GetCalCount(self.session, cal_type, ctypes.byref(cal_count))
        return cal_count.value

    def get_dmm_dev_temp(self):
        """
        Returns the current temperature of the NI 4070/4071/4072.
        :return: dbl, temperature in deg Celsius
        """
        reserved_str = ctypes.create_string_buffer("".encode('utf-8'))
        temp = ctypes.c_double()
        self.dll.niDMM_GetDevTemp(self.session, reserved_str, ctypes.byref(temp))
        return temp.value

    def get_last_cal_temp(self, internal=True):
        """
        Returns the temperature during the last calibration procedure on the NI 4070/4071/4072.
        :param internal: bool, True for internal, False for external
        :return: dbl, temperature in deg C
        """
        cal_type = ctypes.c_int32(1)
        if internal:
            cal_type = ctypes.c_int32(0)
        temp = ctypes.c_double()
        self.dll.niDMM_GetLastCalTemp(self.session, cal_type, ctypes.byref(temp))
        return temp.value

    def get_cal_date_and_time(self, internal=True):
        """
        Returns the temperature during the last calibration procedure on the NI 4070/4071/4072.
        :param internal: bool, True for internal, False for external
        :return: datestr, date
        """
        cal_type = ctypes.c_int32(1)
        if internal:
            cal_type = ctypes.c_int32(0)
        month = ctypes.c_int32()
        day = ctypes.c_int32()
        year = ctypes.c_int32()
        hour = ctypes.c_int32()
        minute = ctypes.c_int32()
        self.dll.niDMM_GetCalDateAndTime(self.session, cal_type,
                                         ctypes.byref(month), ctypes.byref(day), ctypes.byref(year),
                                         ctypes.byref(hour), ctypes.byref(minute))
        date = datetime.datetime(
            month=month.value, day=day.value, year=year.value, hour=hour.value, minute=minute.value)
        date_str = date.strftime('%Y-%m-%d %H:%m')
        return date_str, date

    ''' property Node operations: '''

    def read_property_node(self, property_type, attr_id, name_str="", attr_base_str='IVI_SPECIFIC_PUBLIC_ATTR_BASE'):
        """
        read an attribute with a given id and a given type. Both can be found in the nidmm.h File if necessary.
        :param attr_base_str: str, name of the IVI ATTR Base
        :param property_type: ctypes.type
        :param name_str: Some attributes are unique for each channel. For these, pass the name of the channel.
         Other attributes are unique for each switch. Pass VI_NULL or an empty string for this parameter.
          The default value is an empty string.
        :param attr_id: int, id of the desired attribute. Can be found in the nidmm.h File
        :return: value of the readback, type depends on input
        """
        ivi_attr_base = 1000000
        bases = {'IVI_SPECIFIC_PUBLIC_ATTR_BASE': 150000 + ivi_attr_base,
                 'IVI_SPECIFIC_PRIVATE_ATTR_BASE': 200000 + ivi_attr_base,
                 'IVI_CLASS_PUBLIC_ATTR_BASE': ivi_attr_base + 250000}
        # from header files:
        # nidmm.h:
        # define NIDMM_ATTR_BASE            IVI_SPECIFIC_PUBLIC_ATTR_BASE
        # define NIDMM_ATTR_PRIVATE_BASE             IVI_SPECIFIC_PRIVATE_ATTR_BASE
        # ivi.h:
        # define IVI_ATTR_BASE                   1000000
        # define IVI_SPECIFIC_PUBLIC_ATTR_BASE   (IVI_ATTR_BASE + 150000)
        # /* base for public attributes of specific drivers */
        # define IVI_SPECIFIC_PRIVATE_ATTR_BASE  (IVI_ATTR_BASE + 200000)
        #    /* base for private attributes of specific drivers */
        attr_base = bases[attr_base_str]
        attr_id += attr_base
        attr_id = ctypes.c_int32(attr_id)
        name = ctypes.create_string_buffer(name_str.encode('utf-8'), 256)
        if isinstance(property_type, ctypes.c_int32):
            read_back = ctypes.c_int32()
            self.get_error_message(
                self.dll.niDMM_GetAttributeViInt32(self.session, name, attr_id, ctypes.byref(read_back)))
            return read_back.value
        elif isinstance(property_type, ctypes.c_double):
            read_back = ctypes.c_double()
            self.get_error_message(
                self.dll.niDMM_GetAttributeViReal64(self.session, name, attr_id, ctypes.byref(read_back)))
            return read_back.value
        elif isinstance(property_type, ctypes.c_char):
            read_back = ctypes.create_string_buffer('', 256)
            self.get_error_message(
                self.dll.niDMM_GetAttributeViString(self.session, name, attr_id, ctypes.byref(read_back)))
            return read_back.value.decode('utf-8')
        elif isinstance(property_type, ctypes.c_bool):
            read_back = ctypes.c_bool()
            self.get_error_message(
                self.dll.niDMM_GetAttributeViBoolean(self.session, name, attr_id, ctypes.byref(read_back)))
            return read_back.value

    def set_property_node(self, set_val, attr_id, name_str="", attr_base_str='IVI_SPECIFIC_PUBLIC_ATTR_BASE'):
        """
        set an attribute with a given id and a given type. Both can be found in the nidmm.h File if necessary.
        :param set_val: ctypes.c_double etc. object, with the desired value
        :param attr_id: int, id of the desired attribute. Can be found in the nidmm.h File
        :param name_str: Some attributes are unique for each channel. For these, pass the name of the channel.
         Other attributes are unique for each switch. Pass VI_NULL or an empty string for this parameter.
          The default value is an empty string.
        :param attr_base_str: str, name of the IVI ATTR Base
        """
        ivi_attr_base = 1000000
        bases = {'IVI_SPECIFIC_PUBLIC_ATTR_BASE': 150000 + ivi_attr_base,
                 'IVI_SPECIFIC_PRIVATE_ATTR_BASE': 200000 + ivi_attr_base,
                 'IVI_CLASS_PUBLIC_ATTR_BASE': ivi_attr_base + 250000}
        # from header files:
        # nidmm.h:
        # define NIDMM_ATTR_BASE            IVI_SPECIFIC_PUBLIC_ATTR_BASE
        # define NIDMM_ATTR_PRIVATE_BASE             IVI_SPECIFIC_PRIVATE_ATTR_BASE
        # ivi.h:
        # define IVI_ATTR_BASE                   1000000
        # define IVI_SPECIFIC_PUBLIC_ATTR_BASE   (IVI_ATTR_BASE + 150000)
        # /* base for public attributes of specific drivers */
        # define IVI_SPECIFIC_PRIVATE_ATTR_BASE  (IVI_ATTR_BASE + 200000)
        #    /* base for private attributes of specific drivers */
        attr_base = bases[attr_base_str]
        attr_id += attr_base
        attr_id = ctypes.c_int32(attr_id)
        name = ctypes.create_string_buffer(name_str.encode('utf-8'), 256)
        if isinstance(set_val, ctypes.c_int32):
            self.get_error_message(self.dll.niDMM_SetAttributeViInt32(self.session, name, attr_id, set_val))
        elif isinstance(set_val, ctypes.c_double):
            self.get_error_message(self.dll.niDMM_SetAttributeViReal64(self.session, name, attr_id, set_val))
        elif isinstance(set_val, ctypes.c_char):
            self.get_error_message(self.dll.niDMM_SetAttributeViString(self.session, name, attr_id, set_val))
        elif isinstance(set_val, ctypes.c_bool):
            self.get_error_message(self.dll.niDMM_SetAttributeViBoolean(self.session, name, attr_id, set_val))

    ''' self written functions (e.g. encapsulating property nodes) '''

    def set_input_resistance(self, greater_10_g_ohm=True):
        """
        function to set the input resistance of the NI-4071
        :param greater_10_g_ohm: bool,
            True if you want an input resistance higher than 10GOhm
            False if you want 10MOhm input resistance

         NOTE: >10 GOhm only supported until 10V range!
        """
        self.config_dict['highInputResistanceTrue'] = greater_10_g_ohm
        NIDMM_VAL_1_MEGAOHM = 1000000.0
        NIDMM_VAL_10_MEGAOHM = 10000000.0
        NIDMM_VAL_GREATER_THAN_10_GIGAOHM = 10000000000.0
        NIDMM_VAL_RESISTANCE_NA = 0.0
        NIDMM_ATTR_INPUT_RESISTANCE_id = 29
        resistance = ctypes.c_double(NIDMM_VAL_10_MEGAOHM)
        if greater_10_g_ohm:
            resistance = ctypes.c_double(NIDMM_VAL_GREATER_THAN_10_GIGAOHM)
        self.set_property_node(resistance, NIDMM_ATTR_INPUT_RESISTANCE_id)

    def get_input_resistance(self):
        """
        function to get the currently used input resistance.
        :return: (dbl, str),
        (value of the input resistance as defined in nidmm.h, user readable output)
        """
        NIDMM_VAL_1_MEGAOHM = 1000000.0
        NIDMM_VAL_10_MEGAOHM = 10000000.0
        NIDMM_VAL_GREATER_THAN_10_GIGAOHM = 10000000000.0
        NIDMM_VAL_RESISTANCE_NA = 0.0
        NIDMM_ATTR_INPUT_RESISTANCE_id = 29
        resistance_vals = [NIDMM_VAL_1_MEGAOHM, NIDMM_VAL_10_MEGAOHM,
                           NIDMM_VAL_GREATER_THAN_10_GIGAOHM, NIDMM_VAL_RESISTANCE_NA]
        resistance_name = ['1_M_Ohm', '10_M_Ohm', '>10_G_Ohm', 'Not_Available']
        val = self.read_property_node(ctypes.c_double(), NIDMM_ATTR_INPUT_RESISTANCE_id)
        name = resistance_name[resistance_vals.index(val)]
        return val, name

    def get_range(self):
        """
        read the currently used range.
        :return: dbl, value for the range.
        valid ranges: 0.1, 1.0, 10.0, 100.0, 1000.0
        Auto range ON: -1.0
        Auto range OFF: -2.0
        Auto range ONCE: -3.0
        """
        val = self.read_property_node(ctypes.c_double(), 2,
                                      attr_base_str='IVI_CLASS_PUBLIC_ATTR_BASE')
        return val

    def set_range(self, range_val):
        """
        function for only setting the range of the dmm
        :param range_val: dbl, value for the range.
        valid ranges: 0.1, 1.0, 10.0, 100.0, 1000.0
        Auto range ON: -1.0
        Auto range OFF: -2.0
        Auto range ONCE: -3.0
        """
        if isinstance(range_val, float):
            range_val = '%.1f' % range_val
        self.config_dict['range'] = deepcopy(range_val)
        self.set_property_node(ctypes.c_double(float(range_val)), 2,
                               attr_base_str='IVI_CLASS_PUBLIC_ATTR_BASE')

    def set_aperture_time_units(self, in_plc=True):
        """ set the aperture time units to powerline cycles or seconds"""
        if in_plc:
            units = ctypes.c_int32(1)
        else:
            units = ctypes.c_int32(0)
        self.set_property_node(units,
                               attr_id=322,
                               name_str='',
                               attr_base_str='IVI_CLASS_PUBLIC_ATTR_BASE')

    def set_aperture_time(self, nplc):
        """
        this will set the aperture time units to power line cycles and
         then the aperture time itself.
        :param nplc: float, -> c_double
            allowed vals on Ni4071,
             anything between
             8.89µs (0.00044 plc(50Hz) or 0.0005334 plc(60Hz))
             & 149 s (7450 plc(50Hz) or 8.940 plc(60Hz))
            for simplicity, allowed vals are:
                0.1 PLC, 1 PLC, 5 PLC, 10 PLC, and 100 PLC
        """
        self.set_aperture_time_units(True)
        if isinstance(nplc, float):
            nplc = '%.1f' % nplc
        if isinstance(nplc, int):
            nplc = '%d' % nplc
        self.config_dict['nplc'] = deepcopy(nplc)
        self.set_property_node(
            ctypes.c_double(float(nplc)),
            attr_id=321,
            name_str='',
            attr_base_str='IVI_CLASS_PUBLIC_ATTR_BASE'
        )
        logging.debug('setting apperture to %.1f nplc' % float(nplc))
        nplc_r, units_r = self.get_aperture_time_info()
        if units_r != 'seconds':
            freq = self.config_dict.get('powerLineFrequency', '50')
            apptime = nplc_r / float(freq)
        else:
            apptime = nplc_r

        logging.debug('apperture has ben set to: %.1f, units: %s this is %.3f s' % (nplc_r, units_r, apptime))

    def load_from_config_dict(self, config_dict, reset_dev):
        """
        function to load all parameters stored in a config dict to the device.
        Available values can be found by calling emit_config_pars()
        :param config_dict: dict, containing all required values
        :param reset_dev: bool, true for resetting the DMM on startup.
        :return:
        """
        try:
            self.config_dict = deepcopy(config_dict)
            if reset_dev:
                self.reset_dev()
            self.selected_pre_config_name = config_dict.get('preConfName', 'manual')
            dmm_range = config_dict.get('range')
            resolutin = config_dict.get('resolution')
            self.config_measurement(dmm_range, resolutin)
            trig_count = config_dict.get('triggerCount')
            sample_count = config_dict.get('sampleCount')
            trig_src_enum = Ni4071TriggerSources[config_dict.get('triggerSource')]
            sample_interval = config_dict.get('sampleInterval')
            self.config_multi_point_meas(trig_count, sample_count, trig_src_enum, sample_interval)
            auto_z = config_dict.get('autoZero')
            self.config_auto_zero(auto_z)
            self.config_adc_cal(0)
            pwr_line_freq = config_dict.get('powerLineFrequency')
            self.config_power_line_freq(pwr_line_freq)
            trig_delay = config_dict.get('triggerDelay_s', -1.0)
            self.config_trigger(trig_src_enum, trig_delay)
            trig_slope = config_dict.get('triggerSlope')
            if trig_slope == 'falling':
                trig_slope = 1
            else:
                trig_slope = 0
            self.config_trigger_slope(trig_slope)
            self.config_sample_trigger_slope(trig_slope)
            meas_compl_dest_enum = Ni4071MeasCompleteLoc[config_dict.get('measurementCompleteDestination')]
            self.config_meas_complete_dest(meas_compl_dest_enum)
            self.config_meas_complete_slope(0)
            greater_10_g_ohm = config_dict.get('highInputResistanceTrue')
            self.set_input_resistance(greater_10_g_ohm)
            self.set_aperture_time(config_dict.get('nplc', '100'))
            self.get_accuracy()
            # just to be sure this is included:
            self.config_dict['assignment'] = self.config_dict.get('assignment', 'offset')
        except Exception as e:
            logging.error('Exception while loading config to Ni4071: ' + str(e), exc_info=True)

    def emit_config_pars(self):
        """
        function to return all needed parameters for the configuration dictionary and its values.
        This will also be used to automatically generate a gui.
        Use the indicator_or_control_bool to determine if this is only meant for displaying or also for editing.
        True for control
        :return:dict, tuples:
         (name, indicator_or_control_bool, type, certain_value_list)
        """
        config_dict = {
            'range': (
                'range', True, str, ['-3.0', '-2.0', '-1.0', '0.1', '1.0', '10.0', '100.0', '1000.0'],
                self.config_dict['range']),
            'resolution': ('resolution', True, str, ['3.5', '4.5', '5.5', '6.5', '7.5'],
                           self.config_dict['resolution']),
            'triggerCount': ('#trigger events', True, int, range(0, 100000, 1), self.config_dict['triggerCount']),
            'sampleCount': ('#samples', True, int, range(0, 10000, 1), self.config_dict['sampleCount']),
            'autoZero': ('auto zero', True, int, [-1, 0, 1, 2], self.config_dict['autoZero']),
            'triggerSource': ('trigger source', True, str,
                              [i.name for i in Ni4071TriggerSources], self.config_dict['triggerSource']),
            'sampleInterval': ('sample Interval [s]', True, float,
                               [-1.0] + [i / 10 for i in range(0, 1000)], self.config_dict['sampleInterval']),
            'powerLineFrequency': ('power line frequency [Hz]', True, str,
                                   ['50.0', '60.0'], self.config_dict['powerLineFrequency']),
            'triggerDelay_s': ('trigger delay [s]', True, float,
                               [-2.0, -1.0] + [i / 10 for i in range(0, 1490)], self.config_dict['triggerDelay_s']),
            'triggerSlope': ('trigger slope', True, str, ['falling', 'rising'], self.config_dict['triggerSlope']),
            'measurementCompleteDestination': ('measurement compl. dest.', True, str,
                                               [i.name for i in Ni4071MeasCompleteLoc] + ['software'],
                                               self.config_dict['measurementCompleteDestination']),
            'highInputResistanceTrue': ('high input resistance', True, bool, [False, True]
                                        , self.config_dict['highInputResistanceTrue']),
            'accuracy': ('accuracy (reading, range)', False, tuple, [], self.config_dict['accuracy']),
            'assignment': ('assignment', True, str, ['offset', 'accVolt'], self.config_dict['assignment']),
            'preConfName': ('pre config name', False, str, [], self.selected_pre_config_name),
            'nplc': ('number of power line cycles', True, str,
                     ['0.1', '1', '5', '10', '100'], self.config_dict.get('nplc', '100'))
        }
        return config_dict

    def get_accuracy(self, config_dict=None):
        """
        function to return the accuracy for the current configuration
        the error of the read voltage should be:
        reading +/- (reading * reading_accuracy_float + range_accuracy_float)

        additional noise error is calculated according to:
            http://digital.ni.com/public.nsf/allkb/9FAB5BCA55D1E693862579F00076772D

        rms noise from graph (by eye with origin) (see page 3 Ni4071 specifications):
            0.01 (nplc) = ~2 rms noise (ppm of range)
            0.1 (nplc) = ~0.35 rms noise (ppm of range)
            1 (nplc) = ~0.1 rms noise (ppm of range)
            10 (nplc) = ~0.03 rms noise (ppm of range)
            100 (nplc) = ~0.012 rms noise (ppm of range)

        rms noise mutliplier:
            100 mV (range) = 15 range multiplication factor
            1 V (range) = 2 range multiplication factor
            10 V (range) = 1 range multiplication factor
            100 V (range) = 6 range multiplication factor
            1000 V (range) = 1 range multiplication factor

        error is now:
            err_noise_pmm_range = rms_noise_pmm * (range_multiplication_factor ** 2) / 2
        add this to the range_accuracy_float
        :return: tpl, (reading_accuracy_float, range_accuracy_float)
        """
        if config_dict is None:
            config_dict = self.config_dict
        # from Ni4071 specs:
        # 2 Year, 18°C to 28°C, +/-1°C, values in ppm:
        error_dict_2y = {'0.1': (20, 8), '1.0': (15, 0.8), '10.0': (12, 0.5), '100.0': (20, 2), '1000.0': (20, 0.5)}
        # from eye on page 3 in specs:
        rms_noise_ppm_plc = {'0.1': 0.35, '1': 0.1, '5': 0.04, '10': 0.03, '100': 0.012}
        # from specs:
        multiplic = {'0.1': 15, '1.0': 2, '10.0': 1, '100.0': 6, '1000.0': 1}

        dmm_range = config_dict['range']
        dmm_nplc = config_dict.get('nplc', '1')
        if isinstance(dmm_range, float):
            dmm_range = '%.1f' % dmm_range
        if isinstance(dmm_nplc, int):
            dmm_nplc = '%.d' % dmm_nplc
        if isinstance(dmm_nplc, float):
            dmm_nplc = '%.1f' % dmm_nplc
        err_tpl_2y = error_dict_2y.get(dmm_range, None)
        if err_tpl_2y is None:
            # give up and use largest error
            err_tpl_2y = (20, 8)
        reading_accuracy_float, range_accuracy_float = err_tpl_2y
        # return worst accuracy if it cannot be found in dict
        # logging.debug(self.name + ' range accuracy is: %.3f ppm of range' % range_accuracy_float)
        reading_accuracy_float *= 10 ** -6  # ppm
        range_accuracy_float *= 10 ** -6  # ppm
        rang_noise = rms_noise_ppm_plc[dmm_nplc] * (multiplic[dmm_range] ** 2) / 2
        # logging.debug(self.name + ' range noise is %.3f ppm of range' % rang_noise)
        range_accuracy_float += (rang_noise * 10 ** -6)
        range_accuracy_float *= float(dmm_range)
        acc_tpl = (reading_accuracy_float, range_accuracy_float)
        config_dict['accuracy'] = acc_tpl
        return acc_tpl

    def set_to_pre_conf_setting(self, pre_conf_name):
        """
        this will set and arm the dmm for a pre configured setting.
        :param pre_conf_name: str, name of the setting
        :return:
        """
        logging.info('trying to set %s to the config: %s' % (self.name, pre_conf_name))
        if pre_conf_name in self.pre_configs.__members__:
            self.selected_pre_config_name = pre_conf_name
            config_dict = self.pre_configs[pre_conf_name].value
            config_dict['assignment'] = self.config_dict.get('assignment', 'offset')
            self.load_from_config_dict(config_dict, False)
            self.get_accuracy()
            self.initiate_measurement()
        else:
            logging.error(
                'error: could not set the preconfiguration: %s in dmm: %s, because the config does not exist'
                % (pre_conf_name, self.name))

# there are more functions that can be found in the nidmm.h file,
# but those above were the ones in the quick reference and most important ones.
# how to start external calibration??  niDMM_InitExtCal
#           -> not in quick ref! Will not be implemented for now.


# def test_multi():
#     dmm.config_multi_point_meas(1, 4, 1, 0.1)
#     print(dmm.read_multi_point(5))
#
#
# def test_wfm():
#     dmm.conf_waveform_meas(1003, 1.0, 1800000, 100)
#     print(dmm.read_waveform(num_to_read=100))
#
#
# def test_self_test():
#     print(dmm.self_test())
#
#
# if __name__ == "__main__":
#     dmm = Ni4071()
#     print(dmm.readstatus())
#     dmm.config_dict['triggerSource'] = Ni4071TriggerSources.interval.name
#     print(dmm.config_dict['triggerSource'])
#     dmm.load_from_config_dict(dmm.config_dict, True)
#     dmm.initiate_measurement()
#     while True:
#         ret = dmm.fetch_multiple_meas(num_to_read=-1)
#         if ret:
#             print(ret)
#     i = 0
#     # while i < 100:
#     #     print(dmm.get_dmm_dev_temp())
#     #     i += 1
#     #     time.sleep(0.5)
#     # test_multi()
#     # test_wfm()
#     # test_self_test()
#     # print(dmm.revision_query())
#     # print(dmm.get_error_message())
#     # # dmm.self_calibration()
#     # print(dmm.get_calibration_count())
#     # print(dmm.get_cal_date_and_time())
#     # print(dmm.get_last_cal_temp())
#     print(dmm.get_range())
#     dmm.config_measurement(100.0, 7.5, 1)
#     print('app_time:', dmm.get_aperture_time_info())
#     print('meas_time:', dmm.get_meas_period())
#     dmm.config_auto_zero(0)
#     dmm.config_measurement(100.0, 7.5, 1)
#     print('meas_time:', dmm.get_meas_period())
#
#     dmm.config_auto_zero(1)
#     dmm.config_measurement(100.0, 7.5, 1)
#     print('meas_time:', dmm.get_meas_period())
#
#     print(dmm.get_range())
#
#     print(dmm.readstatus())
#     dmm.set_input_resistance(True)
#     print(dmm.get_input_resistance())
#     dmm.set_range(10.0)
#     # print(dmm.read_single_voltage())
#     dmm.set_input_resistance(True)
#     # print(dmm.read_single_voltage())
#     print(dmm.get_input_resistance())
#     print(dmm.get_range())
#     # print(dmm.read_single_voltage())
#     dmm.de_init_dmm()
