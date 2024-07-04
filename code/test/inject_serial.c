#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <termios.h>
#include <time.h>

void inject_data(const char *serial_port, int baud_rate, const char *data, int interval_ms) {
    int fd;
    struct termios tty;
    struct timespec ts = {0, interval_ms * 1000000L}; // Convert milliseconds to nanoseconds

    // Open the serial port
    fd = open(serial_port, O_RDWR | O_NOCTTY | O_SYNC);
    if (fd < 0) {
        perror("Error opening serial port");
        exit(EXIT_FAILURE);
    }

    // Configure the serial port
    memset(&tty, 0, sizeof(tty));
    if (tcgetattr(fd, &tty) != 0) {
        perror("Error getting serial port attributes");
        close(fd);
        exit(EXIT_FAILURE);
    }

    cfsetospeed(&tty, baud_rate);
    cfsetispeed(&tty, baud_rate);

    tty.c_cflag = (tty.c_cflag & ~CSIZE) | CS8; // 8-bit chars
    tty.c_iflag &= ~IGNBRK;                     // disable break processing
    tty.c_lflag = 0;                            // no signaling chars, no echo,
                                                // no canonical processing
    tty.c_oflag = 0;                            // no remapping, no delays
    tty.c_cc[VMIN] = 0;                         // read doesn't block
    tty.c_cc[VTIME] = 5;                        // 0.5 seconds read timeout

    tty.c_iflag &= ~(IXON | IXOFF | IXANY); // shut off xon/xoff ctrl

    tty.c_cflag |= (CLOCAL | CREAD);       // ignore modem controls,
                                           // enable reading
    tty.c_cflag &= ~(PARENB | PARODD);     // shut off parity
    tty.c_cflag |= 0;
    tty.c_cflag &= ~CSTOPB;
    tty.c_cflag &= ~CRTSCTS;

    if (tcsetattr(fd, TCSANOW, &tty) != 0) {
        perror("Error setting serial port attributes");
        close(fd);
        exit(EXIT_FAILURE);
    }

    // Inject data every interval_ms milliseconds
    while (1) {
        int len = write(fd, data, strlen(data));
        if (len < 0) {
            perror("Error writing to serial port");
            close(fd);
            exit(EXIT_FAILURE);
        }

        //printf("Sent: %s\n", data);

        // Sleep for interval_ms milliseconds
        nanosleep(&ts, NULL);
    }

    close(fd);
}

int main(int argc, char *argv[]) {
    if (argc != 5) {
        fprintf(stderr, "Usage: %s <serial_port> <baud_rate> <data> <interval_ms>\n", argv[0]);
        exit(EXIT_FAILURE);
    }

    const char *serial_port = argv[1];
    int baud_rate = atoi(argv[2]);
    const char *data = argv[3];
    int interval_ms = atoi(argv[4]);

    inject_data(serial_port, baud_rate, data, interval_ms);

    return 0;
}
