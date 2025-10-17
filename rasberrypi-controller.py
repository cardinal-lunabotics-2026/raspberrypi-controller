# Standard Imports
import time
import socket

# Third Part Imports
import serial

# Create server socket and wait until a client connects to it
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind(("10.16.62.101", 60500))
server_socket.listen()
print("Waiting for connection")

# Identify the client
client_socket, addr = server_socket.accept()
print("Client connected at " + str(addr))

try:
    # Establish Serial Port
    arduino = serial.Serial(port='COM3', baudrate=9600)

    # Attempt to communicate over port
    # If port can not be connected to SerialException gets thrown
    print("Connecting...")
    time.sleep(1)
    print("Connected to Arduino (Press 'x' to exit loop)")
    arduino.read_all()

    # Store message
    arduino_out = ""

    # Start communication loop
    # TEMP break loop with x key
    while arduino_out != "x":
        arduino_out = client_socket.recv(1024).decode().strip()
        if arduino_out == 'x':
            break

        # Send arduino the command in bytes over serial
        arduino.write(arduino_out.encode("utf-8"))
        # Wait for response back from arduino
        time.sleep(0.2)
        # Print response
        arduino_in = arduino.read_all()
        print(arduino_in.decode("utf-8"))
        client_socket.sendall(arduino_in)

except serial.SerialException:
    print("Unable to connect")

except ConnectionError:
    print("Client Disconnected")

