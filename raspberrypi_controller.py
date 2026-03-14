'''
The RaspberryPi controller. Interfaces with the Arduino via serial,
    and the mission control PC over a wireless TCP connection.
Made: 10/9/25
Edited: 10/02/26
Authors: James Meyers
Co-Author: Tausif Ahmed
'''

# Standard Imports
import time
import socket

# Third Part Imports
import serial

# glob is used to look for the ACM/USB (Arduino port)
import glob

# listen on all interfaces, so MCC can connect over Wi-Fi/Ethernet
HOST = "0.0.0.0"
PORT = 60500 # Must match what MCC is trying to connect to
BAUD = 57600

# Arduino port lookup
# Note: rather than hardcoding the port name, it will now look for the serial port (in case the name changes)
def find_serial_ports () -> list[str]:
    # Auto-detect the Arduino serial port on Pi
    ports = glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")
    if not ports:
        raise RuntimeError("No Arduino detected (/dev/ttyACM* or /dev/ttyUSB*).")
    return ports

def initialize_arduino() -> list:
    '''
    Starts connection setup for Arduino on the Pi.
    Note: if the Arduino is disconnected in any way, it cannot be reconnected!
    Update: If Arduino is unplugged, we re-detect the port and reconnect.
    '''
    # Open Arduino serial port and return the port
    # Assign the auto-detected Arduino port
    ports = find_serial_ports()
    right_arduino = left_arduino = linear_arduino = None
    for port in ports:
        temp = serial.Serial(port=port, baudrate=BAUD, timeout=0.1)
        time.sleep(2)
        response = temp.read_until('\n').decode('utf-8').strip()
        if response == "right":
            right_arduino = serial.Serial(port=port, baudrate=BAUD, timeout=0.1)
        elif response == "left":
            left_arduino = serial.Serial(port=port, baudrate=BAUD, timeout=0.1)
        elif response == "linear":
            linear_arduino = serial.Serial(port=port, baudrate=BAUD, timeout=0.1)
        print(f"Connecting to {response}-Arduino on {port}...")

    # allow Arduino to reset
    time.sleep(2)
    right_arduino.reset_input_buffer()
    left_arduino.reset_input_buffer()
    linear_arduino.reset_input_buffer()
    print("Connected to Arduinos")
    return right_arduino, left_arduino, linear_arduino

def initialize_connection(server_socket: socket.socket) -> socket.socket:
    '''
    Starts connection setup for a client.
    Used for both initial connection and reconnects.
    '''

    # Wait for client to connect
    server_socket.listen()
    print("Waiting for MCC connection")

    # Handshake with client and return the socket
    client_socket, addr = server_socket.accept()
    print("Client connected at " + str(addr))
    return client_socket

def connection_loop(right_arduino: serial.Serial, left_arduino: serial.Serial, linear_arduino: serial.Serial, client_socket: socket.socket) -> bool:
    '''
    Main communication loop with Arduino, RaspberryPi, and mission control PC

    [SWAP THE INPUT GATHERING PART FOR TAUSIF'S]

    '''

    # Grab input from client and send to Arduino
    # TCP data can include a partial multi-byte character or random bytes (rare, but it happens).
    # .decode() can throw a UnicodeDecodeError and crash the loop
    # "errors=ignore" keeps the bridge running even if one packet contains a weird byte
    arduino_out = client_socket.recv(1024).decode(errors="ignore").strip()

    for line in arduino_out.split(sep="@"):
        # same logic and same output, but less brittle
        line = line.strip()

        if not line:
            continue
        # it was running after the mapping block
        # so if the line is not formatted correctly, it can fail before reaching 'x.'
        # now it will check the format before parsing/mapping (safer exit path even if other parts of the message are corrupted)
        if line == 'x':
            return False

        # comma check (to prevent crashes)
        # TCP does not guarantee to receive the full message properly
        # now instead of crashing, it logs and skips that part
        if "," not in line and ";" not in line:
            print(f"[Pi] Bad line (no comma or semicolon): {line}")
            continue

        # "1" to limit the number of splits, in case there is an extra comma
        values, target_group = line.split(';', 1)
        values = values.strip()
        target_group = target_group.strip()
        values = values.split(',', 1)

        try:
            ivalue = int(float(values[0]))
            ivalue = int(float(values[1]))
        except ValueError:
            print(f"[Pi] Bad value: {ivalue} in line {line}")
            continue

        if target_group is "0":
            left_arduino.write(f"{values[0],values[1]}\n".encode('utf-8'))
            right_arduino.write(f"{values[0],values[1]}\n".encode('utf-8'))
        elif target_group is "1":
            linear_arduino.write(f"{values[0],values[1]}\n".encode('utf-8'))
        elif target_group is "3":
            pass


        print(f"{target_group},{values}")

    time.sleep(0.05)

    # Read output from Arduino and send to client
    if right_arduino.in_waiting > 0:
        right_arduino_output = right_arduino.readline().decode('utf-8')
        print(f"[Right Arduino]: {right_arduino_output}")
    if left_arduino.in_waiting > 0:
        left_arduino_output = left_arduino.readline().decode('utf-8')
        print(f"[Left Arduino]: {left_arduino_output}")
    if linear_arduino.in_waiting > 0:
        linear_arduino_output = linear_arduino.readline().decode('utf-8')
        print(f"[Linear Arduino]: {linear_arduino_output}")

    # A small exception handler in case arduino_in is empty (sendall can throw if the client disconnects;
    # this guards it so the loop survives reconnects.”)

if __name__ == '__main__':
    # Create Server
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # in case we quickly restart the script, this avoids address already in use error
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Hardcoding a specific IP could break when the Pi connects to a different network
    # 0.0.0.0 listen on whatever IP the Pi currently has
    server_socket.bind((HOST, PORT))
    print(f"[Pi] Listening on {HOST}:{PORT}")

    # Initialize vars
    arduino_state = 0
    client_state = 0
    arduino_recconect_counter = 0

    # This is the main program loop
    # Note: This will probably have to be changed if we want to control the robot without a keyboard
    while True:
        # Checks to make sure everything is connected each loop
        try:
            if client_state == 0:
                client_socket = initialize_connection(server_socket)
                client_state = 1

            if arduino_state == 0:
                right_arduino, left_arduino, linear_arduino = initialize_arduino()
                # Simple exception handler in case MCC disconnects at any moment, it prevents a crash during reconnection
                try:
                    client_socket.sendall("Arduinos Connected".encode('utf-8'))
                except Exception:
                    pass
                arduino_state = 1
                arduino_recconect_counter = 0

            if connection_loop(right_arduino, left_arduino, linear_arduino, client_socket) is False:
                break
        # changed a couple of things to make the errors print the reasons
        except serial.SerialException as e:
            if arduino_recconect_counter > 5:
                print("[Pi] Arduino reconnect attempts, exiting...")
                break
            print(f"[Pi] Arduino Serial Error: {e} | Attempting Reconnect")
            time.sleep(1)
            arduino_recconect_counter += 1
            arduino_state = 0

        except ConnectionError:
            print("Client Disconnected")
            client_state = 0
