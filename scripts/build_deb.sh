#!/bin/bash

CURRENT_DATE=$(date +"%Y%m%d_%H%M%S")

# Read the current version
VERSION_FILE="../version.txt"
if [[ -f "$VERSION_FILE" ]]; then
    VERSION=$(cat "$VERSION_FILE")
else
    VERSION="0.1.0"
fi

# Increment the version number
IFS='.' read -r -a VERSION_PARTS <<< "$VERSION"
PATCH=${VERSION_PARTS[2]}
MINOR=${VERSION_PARTS[1]}
MAJOR=${VERSION_PARTS[0]}

if [[ "$PATCH" -lt 9 ]]; then
    PATCH=$((PATCH + 1))
else
    PATCH=0
    MINOR=$((MINOR + 1))
fi

NEW_VERSION="$MAJOR.$MINOR.$PATCH"

# Write the new version back to the version file
echo "$NEW_VERSION" > "$VERSION_FILE"

# Create the directory structure
mkdir -p Serial_Bridge_RPI/DEBIAN
mkdir -p Serial_Bridge_RPI/usr/local/my_app
mkdir -p Serial_Bridge_RPI/etc/systemd/system

# Create the builds directory
mkdir -p ../builds

# Copy application files
cp ../code/app_cli.py Serial_Bridge_RPI/usr/local/my_app/
cp ../code/packet_listener.py Serial_Bridge_RPI/usr/local/my_app/
cp ../configs/config_cli.ini Serial_Bridge_RPI/usr/local/my_app/

# Create the control file
cat <<EOL > Serial_Bridge_RPI/DEBIAN/control
Package: serial-udp-cli
Version: $NEW_VERSION
Section: base
Priority: optional
Architecture: armhf
Depends: python3, python3-serial
Maintainer: Alon Marko <alon7824@gmail.com>
Description: A tool for establishing a serial-to-UDP bridge, allowing serial communication data to be transmitted over a network.
 It includes a listener service that manages the bridge process, ensuring reliable and continuous operation.
EOL

# Create the postinst script to enable and start the service
cat <<EOL > Serial_Bridge_RPI/DEBIAN/postinst
#!/bin/bash
set -e

echo "Reloading systemd manager configuration..."
systemctl daemon-reload

echo "Enabling packet_listener service to start on boot..."
systemctl enable packet_listener

echo "Starting packet_listener service..."
systemctl start packet_listener

echo "packet_listener service has been enabled and started."
EOL

# Make the postinst script executable
chmod 755 Serial_Bridge_RPI/DEBIAN/postinst

# Create the service file
cat <<EOL > Serial_Bridge_RPI/etc/systemd/system/packet_listener.service
[Unit]
Description=Packet Listener Service
After=network.target

[Service]
WorkingDirectory=/usr/local/my_app
ExecStart=/usr/local/my_app/packet_listener.py
Restart=always
User=nobody
Group=nogroup

[Install]
WantedBy=multi-user.target
EOL

# Create a Dockerfile for building the .deb package
cat <<EOL > Dockerfile
FROM debian:bullseye-20220328-slim

# Install necessary tools
RUN apt-get update && apt-get install -y \\
    qemu-user-static \\
    dpkg-dev \\
    debhelper \\
    python3 \\
    python3-pip

# Copy the package directory to the container
COPY Serial_Bridge_RPI /Serial_Bridge_RPI

# Set the working directory
WORKDIR /Serial_Bridge_RPI

# Build the .deb package
RUN dpkg-deb --build --root-owner-group /Serial_Bridge_RPI
EOL

# Register QEMU in Docker
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes

# Build the Docker image, specifying the platform
docker buildx create --use
docker buildx build --platform linux/arm/v7 --load -t bridge-package-builder .

# Run the Docker container to create the .deb package with a timestamp
docker run --rm -v $(pwd)/../builds:/output bridge-package-builder bash -c "dpkg-deb --build --root-owner-group /Serial_Bridge_RPI /output/serial_udp_package_${CURRENT_DATE}.deb"

# Clean up
rm Dockerfile

# Remove the build directory
rm -rf Serial_Bridge_RPI
