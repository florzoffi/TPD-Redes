CC := gcc
CFLAGS := -Wall -Wextra -std=c11 -O2

UDP_CLIENT_SRC := udp/udp_client.c
UDP_SERVER_SRC := udp/udp_server.c
UDP_HEADER := udp/protocol.h

CLIENT_BIN := client
SERVER_BIN := server

.PHONY: all clean

all: $(CLIENT_BIN) $(SERVER_BIN)

$(CLIENT_BIN): $(UDP_CLIENT_SRC) $(UDP_HEADER)
	$(CC) $(CFLAGS) -o $(CLIENT_BIN) $(UDP_CLIENT_SRC)

$(SERVER_BIN): $(UDP_SERVER_SRC) $(UDP_HEADER)
	$(CC) $(CFLAGS) -o $(SERVER_BIN) $(UDP_SERVER_SRC)

clean:
	rm -f $(CLIENT_BIN) $(SERVER_BIN)
