# Open WebUI Benchmark Suite

A comprehensive benchmarking framework for testing Open WebUI performance under various load conditions.

## Overview

This benchmark suite is designed to:

1. **Measure concurrent user capacity** - Test how many users can simultaneously use features like Channels
2. **Identify performance limits** - Find the point where response times degrade
3. **Compare compute profiles** - Test performance across different resource configurations
4. **Generate actionable reports** - Provide detailed metrics and recommendations

## Quick Start

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- A running Open WebUI instance (or use the provided Docker setup)
- Chromium browser (installed automatically via Playwright for UI benchmarks)

### Installation

```bash
cd benchmark
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .

# Install Playwright browsers (required for UI benchmarks)
playwright install chromium
```

### Configuration

Copy the example environment file and configure your admin credentials:

```bash
cp .env.example .env
```

Edit `.env` with your Open WebUI admin credentials:

```dotenv
OPEN_WEBUI_URL=http://localhost:8080
ADMIN_USER_EMAIL=your-admin@example.com
ADMIN_USER_PASSWORD=your-password
```

### Running Benchmarks

1. **Start Open WebUI with benchmark configuration:**

```bash
cd docker
./run.sh default  # Use the default compute profile (2 CPU, 8GB RAM)
```

2. **Run the benchmark:**

```bash
# Run all benchmarks
owb run all

# Run specific benchmarks
owb run chat-api -m 50          # API-based chat benchmark
owb run chat-ui -m 50 --headless # Browser-based chat benchmark
owb run channels-api -m 50      # Channel API concurrency
owb run channels-ws -m 50       # Channel WebSocket benchmark

# Run with options
owb run chat-ui -m 10 --headed --slow-mo 500  # Visual debugging
owb run chat-api -u http://localhost:3000     # Custom URL
owb run channels-api -p cloud_medium          # Specific compute profile
```

3. **View results:**

Results are saved to `results/` in JSON, CSV, and text formats.

## Compute Profiles

Compute profiles define the resource constraints for the Open WebUI container:

| Profile | CPUs | Memory | Use Case |
|---------|------|--------|----------|
| `default` | 2 | 8GB | Local MacBook testing |
| `minimal` | 1 | 4GB | Testing lower bounds |
| `cloud_small` | 2 | 4GB | Small cloud VM |
| `cloud_medium` | 4 | 8GB | Medium cloud VM |
| `cloud_large` | 8 | 16GB | Large cloud VM |

List available profiles:

```bash
owb profiles
```

## Available Benchmarks

### Chat API Concurrency (`chat-api`)

Tests concurrent AI chat performance via the OpenAI-compatible API:

- Creates test users and makes a model publicly available
- Each user sends chat requests via the `/api/chat` endpoint
- Measures response times, throughput, and error rates
- Tests the backend's ability to handle concurrent LLM requests

**Usage:**

```bash
owb run chat-api -m 50 --model gpt-4o-mini
```

### Chat UI Concurrency (`chat-ui`)

Tests concurrent AI chat performance through actual browser UI using Playwright:

- Launches real Chromium browser instances (or contexts)
- Each browser logs in as a different user
- Sends chat messages and waits for streaming responses
- Measures actual user-experienced response times including rendering
- Tests full stack performance: UI, backend, and LLM together

**Usage:**

```bash
# Run in headless mode (default)
owb run chat-ui -m 50 --model gpt-4o-mini

# Run with visible browsers for debugging
owb run chat-ui -m 10 --headed

# Slow down operations for visual inspection
owb run chat-ui -m 5 --headed --slow-mo 500
```

**Configuration:**

```yaml
chat_ui:
  headless: true              # Run browsers in headless mode
  slow_mo: 0                  # Slow down operations by ms (debugging)
  viewport_width: 1280        # Browser viewport width
  viewport_height: 720        # Browser viewport height
  browser_timeout: 30000      # Default timeout in ms
  screenshot_on_error: true   # Capture screenshots on failure
  use_isolated_browsers: false # Use separate browser instances vs contexts
```

**Notes:**
- Browser benchmarks require more resources than API benchmarks
- For high concurrency (50+), use headless mode and browser contexts
- Headed mode is useful for debugging UI issues
- The benchmark measures actual streaming response detection

### Channel Concurrency (`channels-api`)

Tests concurrent user capacity in Open WebUI Channels:

- Creates a test channel
- Progressively adds users (10, 20, 30, ... up to max)
- Each user sends messages at a configured rate
- Measures response times and error rates
- Identifies the maximum sustainable user count

**Configuration options:**

```yaml
channels:
  max_concurrent_users: 100  # Maximum users to test
  user_step_size: 10         # Increment users by this amount
  sustain_time: 30           # Seconds to run at each level
  message_frequency: 0.5     # Messages per second per user
```

### Channel WebSocket (`channels-ws`)

Tests WebSocket scalability for real-time message delivery in Channels:

- Establishes WebSocket connections for multiple users
- Tests real-time message broadcasting
- Measures message delivery latency
- Identifies WebSocket connection limits

## Configuration

Configuration files are located in `config/`:

- `benchmark_config.yaml` - Main benchmark settings
- `compute_profiles.yaml` - Resource profiles for Docker containers

### Environment Variables

All configuration can be set via environment variables (loaded from `.env` file):

| Variable | Description | Default |
|----------|-------------|---------|
| `OPEN_WEBUI_URL` | Open WebUI URL for benchmarking | `http://localhost:8080` |
| Variable | Description | Default |
|----------|-------------|---------|
| `OPEN_WEBUI_URL` | Open WebUI URL | `http://localhost:8080` |
| `OLLAMA_BASE_URL` | Ollama API URL | `http://host.docker.internal:11434` |
| `ENABLE_CHANNELS` | Enable Channels feature | `true` |
| `ADMIN_USER_EMAIL` | Admin email | - |
| `ADMIN_USER_PASSWORD` | Admin password | - |
| `MAX_CONCURRENT_USERS` | Max concurrent users | `50` |
| `USER_STEP_SIZE` | User increment step | `10` |
| `SUSTAIN_TIME_SECONDS` | Test duration per level | `30` |
| `MESSAGE_FREQUENCY` | Messages/sec per user | `0.5` |
| `OPEN_WEBUI_PORT` | Container port | `8080` |
| `CPU_LIMIT` | CPU limit | `2.0` |
| `MEMORY_LIMIT` | Memory limit | `8g` |
1. Create a new file in `benchmark/scenarios/`:

```python
from benchmark.core.base import BaseBenchmark
from benchmark.core.metrics import BenchmarkResult

class MyNewBenchmark(BaseBenchmark):
    name = "My New Benchmark"
    description = "Tests something new"
    version = "1.0.0"
    
    async def setup(self) -> None:
        # Set up test environment
        pass
    
    async def run(self) -> BenchmarkResult:
        # Execute the benchmark
        # Use self.metrics to record timings
        return self.metrics.get_result(self.name)
    
    async def teardown(self) -> None:
        # Clean up
        pass
```

2. Register the benchmark in `benchmark/cli.py`

3. Add configuration options if needed in `config/benchmark_config.yaml`

### Custom Metrics Collection

```python
from benchmark.core.metrics import MetricsCollector

metrics = MetricsCollector()
metrics.start()

# Time individual operations
with metrics.time_operation("my_operation"):
    await do_something()

# Or record manually
metrics.record_timing(
    operation="api_call",
    duration_ms=150.5,
    success=True,
)

metrics.stop()
result = metrics.get_result("My Benchmark")
```

## Understanding Results

### Key Metrics

| Metric | Description | Good Threshold |
|--------|-------------|----------------|
| `avg_response_time_ms` | Average response time | < 2000ms |
| `p95_response_time_ms` | 95th percentile response time | < 3000ms |
| `error_rate_percent` | Percentage of failed requests | < 1% |
| `requests_per_second` | Throughput | > 10 |

### Result Files

- `*.json` - Detailed results for each benchmark run
- `benchmark_results_*.csv` - Combined results in CSV format
- `summary_*.txt` - Human-readable summary

### Interpreting Channel Benchmark Results

The channel benchmark reports:

- **max_sustainable_users**: Maximum users where performance thresholds are met
- **results_by_level**: Performance at each user count level
- **tested_levels**: All user counts that were tested

Example result analysis:

```
Users: 10  | P95: 150ms  | Errors: 0%    | ✓ PASS
Users: 20  | P95: 280ms  | Errors: 0.1%  | ✓ PASS
Users: 30  | P95: 520ms  | Errors: 0.3%  | ✓ PASS
Users: 40  | P95: 1200ms | Errors: 0.8%  | ✓ PASS
Users: 50  | P95: 3500ms | Errors: 2.1%  | ✗ FAIL

Maximum sustainable users: 40
```

## Architecture

```
benchmark/
├── benchmark/
│   ├── core/           # Core framework
│   │   ├── base.py     # Base benchmark class
│   │   ├── config.py   # Configuration management
│   │   ├── metrics.py  # Metrics collection
│   │   └── runner.py   # Benchmark orchestration
│   ├── clients/        # API clients
│   │   ├── http_client.py      # HTTP/REST client
│   │   ├── websocket_client.py # WebSocket client
│   │   └── browser_client.py   # Playwright browser automation
│   ├── scenarios/      # Benchmark implementations
│   │   ├── channels.py # Channel benchmarks
│   │   └── chat_ui.py  # Browser-based chat benchmark
│   ├── utils/          # Utilities
│   │   └── docker.py   # Docker management
│   └── cli.py          # Command-line interface
├── config/             # Configuration files
├── docker/             # Docker Compose for benchmarking
└── results/            # Benchmark output (gitignored)
```

## Dependencies

The benchmark suite reuses Open WebUI dependencies where possible:

**From Open WebUI:**
- `httpx` - HTTP client
- `aiohttp` - Async HTTP
- `python-socketio` - WebSocket client
- `pydantic` - Data validation
- `pandas` - Data analysis

**Benchmark-specific:**
- `playwright` - Browser automation for UI testing
- `locust` - Load testing (optional, for advanced scenarios)
- `rich` - Terminal output
- `docker` - Docker SDK
- `matplotlib` - Plotting results

## Troubleshooting

### Common Issues

1. **Connection refused**: Ensure Open WebUI is running and accessible
2. **Authentication errors**: Check admin credentials in config
3. **Docker resource errors**: Ensure Docker has enough resources allocated
4. **WebSocket timeout**: Increase `websocket_timeout` in config
5. **Browser launch failures**: Run `playwright install chromium` to install browsers
6. **Login timeout in browser tests**: Check that `.env` has correct `ADMIN_USER_NAME` (with quotes if it contains spaces)
7. **High browser concurrency fails**: Use `--headless` mode and ensure sufficient system resources

### Debug Mode

Set logging level to DEBUG:

```bash
export BENCHMARK_LOG_LEVEL=DEBUG
owb run channels
```

## Contributing

When adding new benchmarks:

1. Follow the `BaseBenchmark` interface
2. Add tests for the new benchmark
3. Update configuration schema if needed
4. Add documentation to this README

## License

MIT License - See LICENSE file
