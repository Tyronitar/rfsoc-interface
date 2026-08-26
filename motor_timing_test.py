from telnetlib3.telnetlib import Telnet
import timeit

from pymodbus.client import ModbusTcpClient
import struct


ZEPORT = 23
AKD1 = "169.254.250.165"


def initialize_telnet() -> Telnet:
    # Zenith Angle
    try:
        ser_ze = Telnet(host=AKD1, port=ZEPORT)
        ser_ze.open(host=AKD1, port=ZEPORT)
    except OSError as e:
        raise OSError('Could not communicate with ZA controller. System could not initialize.') from e
        return

    ser_ze.write(b'DRV.ACTIVE\r\n')
    status_string = ser_ze.read_until(b'\r', 0.1).decode()
    status = float(status_string.split('\r')[0])
    if status == 1:
        print('ZA motor connected and software already enabled.')
    else:
        ser_ze.write(b'DRV.EN\r\n')
        sw_en = ser_ze.read_until(b'\r', 0.1)
        print('ZA motor connected and software enabled by Python.')

    # Initialize ZE values
    # self.ze_pps_pos = 0
    # self.get_ser_ze_pps_pos()

    return ser_ze

def get_ser_ze_pos(ser_ze, timeout: float=0.1) -> float | None:
    ser_ze.write('PL.FB\r\n'.encode('ASCII'))
    # TODO: Upgrade to telnetlib3, because this is janky
    # read_until is ALWAYS timing out, despite the string containing a match
    pos_str = ser_ze.read_until(b']', timeout).decode()
    # print(f'ZE position string: {repr(pos_str)}')
    pos = float(pos_str.split(' ')[0].split('>')[-1])
    return pos

def initialize_modbus():
    client = ModbusTcpClient(AKD1, port=ZEPORT)
    client.connect()
    return client

def get_modbus_ze_pos(client: ModbusTcpClient) -> float | None:
    rr = client.read_holding_registers(
        address=588,
        count=4,
    )

    if rr.isError():
        raise ConnectionError('Modbus read error when attempting to get ZE position.')

    raw_bytes = struct.pack('>HH', rr.registers[0], rr.registers[1])
    value = struct.unpack('>i', raw_bytes)[0]

    return value

if __name__ == "__main__":
    modbus = initialize_modbus()
    pos = get_modbus_ze_pos(modbus)

    print(f'Modbus: ZE position is {pos}')


    # ser_ze = initialize_telnet()
    # ser_ze.write(b'MODBUS.ADDR\r\n')
    # status = ser_ze.read_until(b'\r\n', 0.1).decode()
    # print(f'Telnet3: response: {status}')

    # # pos = get_ser_ze_pos(ser_ze, timeout=0.1)
    # # print(f'Telnet3: ZE position is {pos}')
    # start = timeit.default_timer()
    # n_repeats = 10
    # elapsed_time = timeit.timeit('get_ser_ze_pos(ser_ze, timeout=0.1)', globals=globals(), number=n_repeats)
    # print(f'Telnet3: Average time over {n_repeats} repeats: {elapsed_time / n_repeats*1e3:.1f} milliseconds')

