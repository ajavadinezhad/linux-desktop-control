CC ?= cc
CFLAGS ?= -O2
CFLAGS += -std=c11 -Wall -Wextra -Werror -fstack-protector-strong -D_FORTIFY_SOURCE=2
LDFLAGS += -Wl,-z,relro,-z,now

.PHONY: all test clean
all: broker
broker: broker.c
	$(CC) $(CFLAGS) $< -o $@ $(LDFLAGS)
test:
	python3 test_broker.py
clean:
	rm -f broker
