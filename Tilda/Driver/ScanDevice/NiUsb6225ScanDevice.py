"""
Created on 2026-02-17

Local scan-device driver for NI USB-6225 analog outputs.
"""

import logging

import numpy as np

from Tilda.Driver.ScanDevice.BaseTildaScanDeviceControl import BaseTildaScanDeviceControl
from Tilda.PolliFit.Measurement.SpecData import SpecDataXAxisUnits as Units

try:
    import nidaqmx
    from nidaqmx.system import System as NISystem
except Exception:
    nidaqmx = None
    NISystem = None


class NiUsb6225ScanDevice(BaseTildaScanDeviceControl):
    """
    Local scan-device wrapper that writes scan values to an NI USB-6225 AO channel.
    """

    DEV_TYPE = 'NI_USB6225_AO'
    DEV_CLASS = 'Triton'
    SET_VAL_LIMIT = (-10.0, 10.0)
    STEP_SIZE_LIMIT = (1e-6, 20.0)

    def __init__(self, channel_name=None):
        super(NiUsb6225ScanDevice, self).__init__()
        self._task = None
        self._selected_channel = channel_name or self.default_channel()
        self._abort_scan = False
        self._scan_status = 'initialized'

        self._sc_start = 0.0
        self._sc_stop = 0.0
        self._sc_step = 0.0
        self._sc_num_steps = 0
        self._sc_num_scans = 0
        self._sc_invert = False
        self._sc_vals = []

        self._cur_step = -1
        self._cur_scan = 0
        self._percent_complete = 0.0
        self._scan_complete = False

    @classmethod
    def _nidaq_available(cls):
        return nidaqmx is not None and NISystem is not None

    @classmethod
    def available_channels(cls):
        """
        Return all AO physical channels from detected USB-6225 devices.
        """
        if not cls._nidaq_available():
            return []
        ret = []
        try:
            for dev in NISystem.local().devices:
                dev_type = str(getattr(dev, 'product_type', '') or '')
                if 'USB-6225' in dev_type or '6225' in dev_type:
                    for ch in dev.ao_physical_chans:
                        ret.append(ch.name)
        except Exception as exc:
            logging.error('failed to list NI USB-6225 channels: %s', exc, exc_info=True)
        return sorted(set(ret))

    @classmethod
    def default_channel(cls):
        channels = cls.available_channels()
        return channels[0] if channels else ''

    def _coerce_voltage(self, voltage):
        lo, hi = self.SET_VAL_LIMIT
        return float(min(max(float(voltage), lo), hi))

    def _ensure_selected_channel(self):
        channels = self.available_channels()
        if self._selected_channel and self._selected_channel in channels:
            return self._selected_channel
        if self._selected_channel and not channels:
            # Keep configured channel if discovery fails but channel is explicitly set.
            return self._selected_channel
        self._selected_channel = channels[0] if channels else ''
        return self._selected_channel

    def _ensure_task(self):
        if not self._nidaq_available():
            raise RuntimeError('nidaqmx is not available in this python environment')

        channel = self._ensure_selected_channel()
        if not channel:
            raise RuntimeError('no NI USB-6225 AO channel available')

        if self._task is None:
            self._task = nidaqmx.Task('TildaNiUsb6225Ao')
            self._task.ao_channels.add_ao_voltage_chan(
                channel,
                min_val=self.SET_VAL_LIMIT[0],
                max_val=self.SET_VAL_LIMIT[1]
            )
            logging.info('initialized NI USB-6225 AO task on channel %s', channel)

    def _write_voltage(self, voltage):
        set_val = self._coerce_voltage(voltage)
        self._ensure_task()
        self._task.write(set_val, auto_start=True)
        return set_val

    def available_scan_dev_types(self):
        return [self.DEV_TYPE]

    def available_scan_dev_names_by_type(self, dev_type):
        if dev_type != self.DEV_TYPE:
            return []
        names = self.available_channels()
        return names

    def return_scan_dev_info(self, dev_type=None, dev_name=None):
        req_type = dev_type if dev_type is not None else self.DEV_TYPE
        req_name = dev_name if dev_name is not None else self._selected_channel
        return {
            'name': req_name,
            'type': req_type,
            'devClass': self.DEV_CLASS,
            'stepUnitName': Units.line_volts.name,
            'start': self._sc_start,
            'stop': self._sc_stop,
            'stepSize': self._sc_step,
            'preScanSetPoint': None,
            'postScanSetPoint': None,
            'timeout_s': 10.0,
            'setValLimit': self.SET_VAL_LIMIT,
            'stepSizeLimit': self.STEP_SIZE_LIMIT
        }

    def setup_scan_in_scan_dev(self, start, stepsize, num_of_steps, num_of_scans, invert_in_odd_scans):
        """
        Store scan settings and build one full-scan voltage array.
        """
        self._abort_scan = False
        self._scan_complete = False
        self._scan_status = 'setupForScan'
        self._cur_step = -1
        self._cur_scan = 0
        self._percent_complete = 0.0

        self._sc_num_steps = max(1, int(num_of_steps))
        self._sc_num_scans = max(1, int(num_of_scans))
        self._sc_invert = bool(invert_in_odd_scans)

        start_v = self._coerce_voltage(start)
        step_v = float(stepsize)
        stop_v = self._coerce_voltage(start_v + (self._sc_num_steps - 1) * step_v)
        vals, ret_step = np.linspace(start_v, stop_v, self._sc_num_steps, retstep=True)

        self._sc_start = float(start_v)
        self._sc_stop = float(stop_v)
        self._sc_step = float(ret_step)
        self._sc_vals = vals.tolist()

        self.scan_dev_has_setup_these_pars_pyqtsig.emit({
            'unitName': Units.line_volts.name,
            'start': self._sc_start,
            'stop': self._sc_stop,
            'stepSize': self._sc_step,
            'stepNums': self._sc_num_steps,
            'valsArrrayOneScan': self._sc_vals
        })

    def _update_scan_completion(self):
        if self._sc_invert and self._cur_scan % 2 != 0:
            completed = (self._sc_num_steps - self._cur_step) + self._cur_scan * self._sc_num_steps
        else:
            completed = (self._cur_step + 1) + self._cur_scan * self._sc_num_steps
        total = self._sc_num_steps * self._sc_num_scans
        self._percent_complete = completed / total if total else 1.0
        self._scan_complete = completed >= total
        if self._scan_complete:
            self._scan_status = 'complete'

    def request_next_step(self):
        """
        Set the next voltage immediately and emit progress to ScanMain.
        """
        if self._abort_scan:
            self._scan_status = 'aborted'
            return False

        if self._scan_complete:
            logging.warning('NI USB-6225: next step requested after scan completion')
            return False

        invert = self._sc_invert and self._cur_scan % 2 != 0
        scan_dir = -1 if invert else 1

        if self._cur_step + scan_dir > self._sc_num_steps - 1:
            self._cur_scan += 1
            invert = self._sc_invert and self._cur_scan % 2 != 0
            self._cur_step = self._sc_num_steps - 1 if invert else 0
        elif invert and self._cur_step + scan_dir < 0:
            self._cur_scan += 1
            self._cur_step = 0
        else:
            self._cur_step += scan_dir

        if self._cur_scan >= self._sc_num_scans:
            self._scan_complete = True
            self._scan_status = 'complete'
            return False

        self._scan_status = 'scanning'
        set_val = self._write_voltage(self._sc_vals[self._cur_step])
        self._update_scan_completion()

        self.scan_dev_has_set_a_new_step_pyqtsig.emit({
            'curStep': self._cur_step,
            'curScan': self._cur_scan,
            'percentOfScan': self._percent_complete,
            'curStepVal': set_val,
            'scanStatus': self._scan_status
        })
        return True

    def abort_scan(self):
        self._abort_scan = True
        self._scan_status = 'aborted'
        return True

    def set_pre_scan_masurement_setpoint(self, set_val):
        if set_val is None:
            return True
        try:
            self._write_voltage(set_val)
            return True
        except Exception as exc:
            logging.error('failed to set NI USB-6225 pre/post setpoint: %s', exc, exc_info=True)
            return False

    def deinit_scan_dev(self):
        if self._task is not None:
            try:
                self._task.close()
            except Exception as exc:
                logging.error('failed to close NI USB-6225 AO task: %s', exc, exc_info=True)
            finally:
                self._task = None

    def __del__(self):
        try:
            self.deinit_scan_dev()
        except Exception:
            pass
