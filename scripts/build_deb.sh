#!/bin/bash

CURRENT_DATE=$(date +"%Y%m%d_%H%M%S")

# Create the directory structure
mkdir -p Serial_Bridge_RPI/DEBIAN
mkdir -p Serial_Bridge_RPI/usr/local/my_app
mkdir -p Serial_Bridge_RPI/etc/systemd/system

# Create the builds directory
mkdir -p ../builds

# Copy application files
cp ../code/app_cli_2_con.py Serial_Bridge_RPI/usr/local/my_app/
cp ../code/packet_listener.py Serial_Bridge_RPI/usr/local/my_app/
cp ../config/config_cli.ini Serial_Bridge_RPI/usr/local/my_app/

# Create the control file
cat <<EOL > Serial_Bridge_RPI/DEBIAN/control
Package: serial-udp-cli
Version: 0.1
Section: base
Priority: optional
Architecture: armhf
Depends: python3, python3-serial
Maintainer: Alon Marko <alon7824@gmail.com>
Description: a tool for establishing a serial-to-UDP bridge, allowing serial communication data to be transmitted over a network.
 It includes a listener service that manages the bridge process, ensuring reliable and continuous operation.
EOL

# Create the service file
cat <<EOL > Serial_Bridge_RPI/etc/systemd/system/packet_listener.service
[Unit]
Description=Packet Listener Service
After=network.target

[Service]
ExecStart=/usr/local/my_app/packet_listener.py
Restart=always
User=nobody
Group=nogroup

[Install]
WantedBy=multi-user.target
EOL

# Create a Dockerfile for building the .deb package
cat <<EOL > Dockerfile
FROM arm32v7/ubuntu:latest

# Install necessary tools
RUN apt-get update && apt-get install -y \\
    qemu-user-static \\
    dpkg-dev \\
    debhelper \\
    python3 \\
    python3-serial

# Copy the package directory to the container
COPY Serial_Bridge_RPI /Serial_Bridge_RPI

# Set the working directory
WORKDIR /Serial_Bridge_RPI

# Build the .deb package
RUN dpkg-deb --build /Serial_Bridge_RPI
EOL

# Register QEMU in Docker
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes

# Build the Docker image
docker build -t bridge-package-builder .

# Run the Docker container to create the .deb package with a timestamp
docker run --rm -v $(pwd)/../builds:/output bridge-package-builder bash -c "dpkg-deb --build /Serial_Bridge_RPI /output/serial_udp_package_${CURRENT_DATE}.deb"
# Clean up
rm Dockerfile

# Remove the build directory
rm -rf Serial_Bridge_RPI
