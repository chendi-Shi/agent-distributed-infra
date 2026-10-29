"""
Prometheus HTTP Server
Exposes /metrics endpoint for Prometheus scraping
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging
from monitoring.metrics import get_metrics_collector


logger = logging.getLogger(__name__)


class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler for Prometheus metrics endpoint"""

    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/metrics':
            self.send_metrics()
        elif self.path == '/health':
            self.send_health()
        else:
            self.send_error(404)

    def send_metrics(self):
        """Send Prometheus metrics"""
        try:
            collector = get_metrics_collector()
            metrics_data = collector.export_metrics()

            self.send_response(200)
            self.send_header('Content-Type', collector.get_content_type())
            self.end_headers()
            self.wfile.write(metrics_data)

        except Exception as e:
            logger.error(f"Error exporting metrics: {e}")
            self.send_error(500)

    def send_health(self):
        """Send health check response"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"status": "healthy"}')

    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.debug(f"{self.client_address[0]} - {format % args}")


class PrometheusServer:
    """Prometheus metrics HTTP server"""

    def __init__(self, host: str = '0.0.0.0', port: int = 9090):
        self.host = host
        self.port = port
        self.server = None
        self.logger = logging.getLogger("PrometheusServer")

    def start(self):
        """Start the metrics server"""
        try:
            self.server = HTTPServer((self.host, self.port), MetricsHandler)
            self.logger.info(f"Prometheus metrics server started on {self.host}:{self.port}")
            self.logger.info(f"Metrics endpoint: http://{self.host}:{self.port}/metrics")
            self.server.serve_forever()

        except KeyboardInterrupt:
            self.logger.info("Server interrupted by user")
            self.stop()
        except Exception as e:
            self.logger.error(f"Error starting server: {e}")
            raise

    def stop(self):
        """Stop the metrics server"""
        if self.server:
            self.server.shutdown()
            self.logger.info("Prometheus server stopped")


def start_metrics_server(host: str = '0.0.0.0', port: int = 9090):
    """Start Prometheus metrics server (convenience function)"""
    server = PrometheusServer(host, port)
    server.start()


if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Start server
    start_metrics_server()
