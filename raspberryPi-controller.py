# Standard Imports
import time
import socket

# Third Part Imports
import serial

# Global Vars
server_socket = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
server_socket.bind(("10.16.62.101", 60500))
client_socket = None

def connection_loop():
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


def initialize_connection():
    global client_socket

    server_socket.listen()
    print("Waiting for connection")

    client_socket, addr = server_socket.accept()
    print("Client connected at " + str(addr))

    connection_loop()

if __name__ == '__main__':
    initialize_connection()