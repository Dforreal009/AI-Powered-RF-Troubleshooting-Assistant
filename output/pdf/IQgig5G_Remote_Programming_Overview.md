# IQgig-5G Model B: What You Need to Understand

This guide explains the minimum practical knowledge needed to operate the LitePoint IQgig-5G Model B from Python using SCPI commands.

## 1. The tester is three systems working together

- **VSG (Vector Signal Generator):** Generates and transmits the configured RF waveform.
- **VSA (Vector Signal Analyzer):** Captures the incoming RF signal and calculates measurements such as EVM, power, occupied bandwidth, ACLR, spectrum emission mask, carrier leakage, and in-band emissions.
- **ROUT (Routing):** Connects the tester's physical RF ports to VSG and VSA resources. A test cannot work correctly if the required resources are routed to the wrong ports.

The normal measurement path is:

`waveform generation -> RF routing -> signal capture -> 5G demodulation -> calculation -> result fetch`

## 2. Important operating limits

| Item | IQgig-5G Model B capability |
| --- | --- |
| RF frequency range | 23 GHz to 45 GHz |
| Maximum capture/modulation bandwidth | 1.7 GHz |
| VSA input range | Up to +20 dBm CW |
| VSG output range | Typically +10 dBm to -70 dBm below 40 GHz |
| RF ports | Two or four bidirectional 2.4 mm ports, depending on configuration |
| System warm-up | 60 minutes before specifications are valid |
| Default network address | `192.168.100.254` |

Reference level, path-loss correction, cable condition, port routing, calibration state, and warm-up time can all change the apparent measurement result. They must be recorded with every diagnostic example.

## 3. Python controls the tester by sending SCPI over TCP

Python does not replace SCPI. It opens a TCP connection and sends the same SCPI program messages that an engineer would enter manually.

The tester exposes three TCP servers:

| Port | Purpose |
| --- | --- |
| `24000` | Command/control: normal SCPI commands and queries |
| `24001` | Service request: asynchronous status notification |
| `24002` | Device clear: clears the instrument independently of the command connection |

For ordinary automation, start with port `24000`.

SCPI messages are ASCII text. A program message must end with a line feed (`\n`), and a response message also ends with a line feed. A query is a command ending in `?`, such as `*IDN?`.

## 4. Minimal Python connection

```python
import socket


def query(sock, command):
    sock.sendall((command + "\n").encode("ascii"))
    response = b""
    while not response.endswith(b"\n"):
        chunk = sock.recv(65536)
        if not chunk:
            raise ConnectionError("Tester closed the connection")
        response += chunk
    return response.decode("ascii").strip()


with socket.create_connection(("192.168.100.254", 24000), timeout=10) as tester:
    print(query(tester, "*IDN?"))
```

Only read a response after sending a query. A normal setting command does not necessarily return anything, so attempting to read afterward can cause the program to wait until it times out.

## 5. The SCPI test sequence

The supplied command example follows this structure:

1. **Select the channel and technology module** with commands such as `CHAN1;5G`.
2. **Route physical ports** to resources, for example connecting `RF1A` to `VSG1` and `RF2A` to `VSA1`.
3. **Load and start the waveform** with `VSG1;WAVE:LOAD ...` and `WAVE:EXEC ON`.
4. **Set the generator power** with `VSG1;POW:LEV ...`.
5. **Configure the analyzer capture**, including capture time, frequency, sampling rate, reference level, and trigger behavior.
6. **Reset and configure 5G analysis**, including FR1/FR2, uplink/downlink, bandwidth, modulation, resource blocks, DMRS, MIMO, and synchronization settings.
7. **Start the capture** with `VSA1;INIT`.
8. **Run calculations**, such as transmit quality, power, spectrum, or CCDF.
9. **Fetch the calculated results** using the appropriate `FETCh...?` queries.

Calculation and result retrieval are different operations. A `CALC...` command asks the tester to compute a measurement; a `FETCh...?` query returns the result. The supplied example performs calculations but does not show the result-fetching layer that the Python program will need.

## 6. Reliability rules for the Python layer

- Begin a session with `*IDN?` and confirm that the expected tester answered.
- Use `*OPC?` or the tester's status system to synchronize long capture and calculation operations.
- Set different timeouts for quick configuration commands and long measurements.
- After a failed operation, read `SYST:ERR:ALL?` and save the complete error response.
- Treat a fetch status code separately from the numeric measurement. A returned number is not automatically a valid result.
- Log every command, response, timestamp, timeout, configuration, and instrument software revision.
- Do not allow two applications to control the same session. External SCPI execution locks the browser GUI to prevent conflicting commands.
- During development, use the dashboard Trace Tool with source `EXT` to compare the Python commands with known-good GUI behavior.
- Always turn off the VSG output and close the socket in cleanup logic, including after exceptions.

## 7. Files that matter most

- `IQgig5GBUserGuideMaster.pdf`: TCP ports, SCPI framing, program messages, queries, and response rules.
- `IQgig5GBQuickStart.pdf`: network setup, GUI locking, Trace Tool, SCPI console, path-loss tables, logs, and diagnostics.
- `IQgig5GBTechnicalSpecs.pdf`: RF ranges, power limits, sampling rates, warm-up, and measurement capabilities.
- `htmldoc/module_5G.html`: exact 5G configuration, calculation, and fetch commands.
- `htmldoc/module_VSA.html`, `module_VSG.html`, and `module_ROUT.html`: analyzer, generator, and routing commands.
- `htmldoc/FetchStatusCodes.html` and `errors.html`: result validity and failure interpretation.
- `SCPI_commanda.txt`: the existing manual test sequence and the starting point for Python automation.

## Sources

- LitePoint, *IQgig-5G Model B User Guide*.
- LitePoint, *IQgig-5G Model B Quick Start Guide*.
- LitePoint, *IQgig-5G Model B Technical Specifications*.
- LitePoint IQgig-5G Model B SCPI HTML reference, revision 1.24.0.288143.
