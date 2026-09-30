CXX ?= g++
CXXFLAGS ?= -O2 -std=c++17 -Wall -Wextra -pthread
LDFLAGS ?=
LIBS_MAIN = -lgpiod

SRC_DIR = src
TOOLS_DIR = tools

MAIN_SRCS = $(SRC_DIR)/common.cpp $(SRC_DIR)/crsf_protocol.cpp $(SRC_DIR)/rangefinder.cpp $(SRC_DIR)/altitude_controller.cpp $(SRC_DIR)/uart.cpp $(SRC_DIR)/telemetry.cpp $(SRC_DIR)/logger.cpp $(SRC_DIR)/main.cpp
MONITOR_SRCS = $(TOOLS_DIR)/monitor.cpp

all: crsf_stack monitor

crsf_stack: $(MAIN_SRCS)
	$(CXX) $(CXXFLAGS) -o $@ $(MAIN_SRCS) $(LDFLAGS) $(LIBS_MAIN)

monitor: $(MONITOR_SRCS)
	$(CXX) $(CXXFLAGS) -o $@ $(MONITOR_SRCS) $(LDFLAGS)

clean:
	rm -f crsf_stack monitor
