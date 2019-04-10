__all__ = ["WhiteLightSourceComponent"]

from pymodbus.client.sync import ModbusTcpClient as ModbusClient
from lsst.ts import salobj
from collections import namedtuple
import time
from pymodbus.exceptions import ConnectionException, ModbusIOException


class WhiteLightSourceComponent():
    """ Class that handles communication with the white light source hardware
        
        Parameters
        ----------
        ip : string
            the IP address of the ADAM 6024 controller
        port : int
            the port number for the ADAM 6024 controller
        
        Attributes
        ----------
        client : ModbusClient
            the pymodbus object representing the ADAM 6024
        bulbHours : float
            uptime of this bulb
        bulbWattHours : float
            uptime in this bulb in watt-hours
        bulbcount : int
            number of bulbs we've had.
        bulbHoursLastUpdate: float
            the time of the last update for bulb uptime
        bulbstate : float
            the current wattage the bulb is at. 

    """

    def __init__(self, ip='140.252.33.160', port=502):
        self.client = ModbusClient(ip, port)
        self.bulbHours = 0  # Read this from EFD when we initialize
        self.bulbWattHours = 0  # This too
        self.bulbCount = 0  # how many bulbs have there been in total?
        self.bulbHoursLastUpdate = time.time()/3600
        self.bulbState = 0

    def setLightPower(self, watts):
        """ Sets the brightness (in watts) on the white light source.


            Parameters
            ----------
            watts : int or float
                Should be in the range of 800-1200 (inclusive)

            Returns
            -------
            None
        """

        targetVoltage = self._wattsToVolts(watts)
        self._writeVoltage(targetVoltage)
        self.bulbState = watts

    def checkStatus(self):
        """ checks 4 analog inputs to see if any of them have
            voltages in excess of 3.0. If so, that LED is lit!
            errorLED communicates error ID by flashing, so if we 
            want to do anything with that, we will need to 
            sample quickly enough to count flashes. Probably not
            going to do this. 

        Parameters
        ----------
        None

        Returns
        -------
        status: NamedTuple containing the current wattage, then
                booleans representing the status LEDs. 
        """
        KiloArcStatus = namedtuple('KiloArcStatus', ['wattage','greenLED','blueLED','redLED','errorLED'])
        
        voltages = self._readVoltage()
        cutoff = 3.0
        
        status = KiloArcStatus(self.bulbState, voltages[0] > cutoff, voltages[1] > cutoff,\
            voltages[2] > cutoff, voltages[3] > cutoff)

        return status

    def _wattsToVolts(self, watts):
        """ calculates what voltage to send (in the range of 1.961v to 5.0v)
            in order to achieve the desired watt output (in the range of
            800w to 1200w) from the Horiba Kiloarc device.

        Parameters
        ----------
        watts : float
            desired wattage for the bulb

        Returns
        -------
        volts : float
            the Kiloarc's input voltage corresponding to the desired output wattage
        """

        output = -4.176993316101 + watts / 130.762
        if output < 0: output = 0 # voltage equation should have a floor of 0. 
        return output

    def _readVoltage(self):
        """ reads the voltage off of ADAM-6024's inputs for channels 0-3.

        Parameters
        ----------
        None

        Returns
        -------
        volts : List of floats
            the voltages on the ADAM's first 4 input channels
        """
        try:
            readout = self.client.read_input_registers(0, 4, unit=1)
            return [self._countsToVolts(r) for r in readout.registers]
        except AttributeError:
            # read_input_registers() *returns* (not raises) a
            # ModbusIOException in the event of loss of ADAM network
            # connectivity, which causes an AttributeError when we try
            # to access the registers field. But the whole thing is
            # really a connectivity problem, so we re-raise it as a
            # ConnectionException, which we know how to handle. Weird 
            # exception handling is a known issue with pymodbus so it
            # may see a fix in a future version, which may require 
            # minor code changes on our part.
            # https://github.com/riptideio/pymodbus/issues/298
            raise ConnectionException

    def _writeVoltage(self, volts):
        """ writes the requested voltage to the ADAM-6024 output register AO0

        Parameters
        ----------
        volts : float
            voltage we want to send out on the ADAM output

        Returns
        -------
        None

        """
        self.client.write_register(10, self._voltsToCounts(volts))

    def _voltsToCounts(self, volts):
        """ discretizes volts for 12-bit ADAM-6024 output

        Parameters
        ----------
        volts : float
            voltage we want to send out on the ADAM output

        Returns
        -------
        counts : integer
            voltage converted into a 12 bit int for ADAM
        """

        vtc = 10/4095
        return int(volts/vtc)

    def _countsToVolts(self, counts):
        """ converts discrete ADAM-6024 input readings into volts

        Parameters
        ----------
        counts : integer
            16-bit integer received from ADAM device

        Returns
        -------
        volts : float
            counts converted into voltage number
        """
        ctv = 20/65535
        return counts * ctv - 10
