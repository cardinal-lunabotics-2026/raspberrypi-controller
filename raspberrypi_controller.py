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
BAUD = 9600

# MAIN CONTROLS MAP
control_lookup_table = {
    "dpv": 1,
    "dph": 2,
    "btna": 3,
    "btnb": 4,
    "btny": 5,
    "btnx": 6
}

# Arduino port lookup
# Note: rather than hardcoding the port name, it will now look for the serial port (in case the name changes)
def find_serial_port () -> str:
    # Auto-detect the Arduino serial port on Pi
    ports = glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")
    if not ports:
        raise RuntimeError("No Arduino detected (/dev/ttyACM* or /dev/ttyUSB*).")
    return ports[0]

def initialize_arduino() -> serial.Serial:
    '''
    Starts connection setup for Arduino on the Pi.
    Note: if the Arduino is disconnected in any way, it cannot be reconnected!
    Update: If Arduino is unplugged, we re-detect the port and reconnect.
    '''
    # Open Arduino serial port and return the port
    # Assign the auto-detected Arduino port
    port = find_serial_port()
    print(f"Connecting to Arduino on {port}...")
    arduino = serial.Serial(port=port, baudrate=BAUD, timeout=0.1)

    # allow Arduino to reset
    time.sleep(2)
    arduino.reset_input_buffer()
    print("Connected to Arduino")
    return arduino

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

def connection_loop(arduino: serial.Serial, client_socket: socket.socket) -> bool:
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
        if "," not in line:
            print(f"[Pi] Bad line (no comma): {line}")
            continue

        # "1" to limit the number of splits, in case there is an extra comma
        control, value = line.split(",", 1)
        control = control.strip()
        value = value.strip()

        # rather than taking anything that comes from the socket as a string
        # Now it sanitizes the input so Arduino receives clean integer commands (-1, 0, 1)
        # prevents crash if a bad value comes in

        if control not in control_lookup_table:
            print(f"[Pi] Unknown control: {control}")
            continue

        try:
            ivalue = int(float(value))
        except ValueError:
            print(f"[Pi] Bad value: {value} in line {line}")
            continue

        control_number = control_lookup_table[control]
        arduino.write(f"{control_number},{ivalue}\n".encode('utf-8'))
        print(f"{control},{ivalue} -> {control_number}, {ivalue}")

    time.sleep(0.05)

    # Read output from Arduino and send to client
    arduino_in = arduino.read_all()

    # A small exception handler in case arduino_in is empty (sendall can throw if the client disconnects;
    # this guards it so the loop survives reconnects.”)
    if arduino_in:
        try:
            client_socket.sendall(arduino_in)
        except Exception:
            pass



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
                arduino = initialize_arduino()
                # Simple exception handler in case MCC disconnects at any moment, it prevents a crash during reconnection
                try:
                    client_socket.sendall("Arduino Connected".encode('utf-8'))
                except Exception:
                    pass
                arduino_state = 1
                arduino_recconect_counter = 0

            if connection_loop(arduino, client_socket) is False:
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
