"""
Created on 04.03.19

@author: simkaufm

Module Description:  for now, dummy class functionality will be left at the fpga
"""

import Tilda.Service.VoltageConversions.VoltageConversions as VCon
from Tilda.Application.Importer import DAC_Calibration
from Tilda.PolliFit.Measurement.SpecData import SpecDataXAxisUnits as Units
from Tilda.Driver.ScanDevice.BaseTildaScanDeviceControl import BaseTildaScanDeviceControl
from Tilda.Driver.ScanDevice.NiUsb6225ScanDevice import NiUsb6225ScanDevice


class AD57X1ScanDev(BaseTildaScanDeviceControl):
    """
    overwrite all functions if wanted else dummy
    """

    def __init__(self):
        super(AD57X1ScanDev, self).__init__()

    def return_scan_dev_info(self, dev_type=None, dev_name=None):
        """
        return the scan device info
        -> currently only one dac available.... adapt maybe if needed
        """
        if dev_type == NiUsb6225ScanDevice.DEV_TYPE:
            return NiUsb6225ScanDevice(dev_name).return_scan_dev_info(dev_type, dev_name)

        draft_scan_dev_dict = {
            'name': DAC_Calibration.dac_name,
            'type': 'AD57X1(DAC)',  # what type of device, e.g. AD5781(DAC) / Matisse (laser)
            'devClass': 'DAC',  # carrier class of the dev, e.g. DAC / Triton
            'stepUnitName': Units.line_volts.name,
            'start': 0.0,
            'stop': 0.0,
            'stepSize': 1.0,
            'preScanSetPoint': None,  # 0 volts
            'postScanSetPoint': None,
            'timeout_s': 10.0,  # timeout in seconds after which step setting is accounted as failure due to timeout,
            # set top 0 for never timing out.
            'setValLimit': (VCon.get_voltage_from_bits(0), VCon.get_voltage_from_bits(VCon.get_max_value_in_bits())),
            'stepSizeLimit': (VCon.get_stepsize_in_volt_from_bits(1), 15.0)
        }
        return draft_scan_dev_dict

    def available_scan_dev_names_by_type(self, type):
        """
        return a list of available AD5781DACs, for the given type of this devClass
        :param type: str, type of the device (e.g. AD5781 / Matisse)
        :return: list of strings with available names
        """
        if type == NiUsb6225ScanDevice.DEV_TYPE:
            return NiUsb6225ScanDevice.available_channels()
        return [self.return_scan_dev_info()['name']]

    def available_scan_dev_types(self):
        """
        return a list of available scan device types for this devClass
        :return: list of strings with available types
        """
        dev_types = [self.return_scan_dev_info()['type']]
        ni_ao_channels = NiUsb6225ScanDevice.available_channels()
        if (ni_ao_channels or NiUsb6225ScanDevice._nidaq_available()) and NiUsb6225ScanDevice.DEV_TYPE not in dev_types:
            dev_types.append(NiUsb6225ScanDevice.DEV_TYPE)
        return dev_types
