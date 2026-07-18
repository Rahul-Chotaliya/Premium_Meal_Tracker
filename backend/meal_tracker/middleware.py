import time
import logging

logger = logging.getLogger('django')

class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()
        
        response = self.get_response(request)
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Log format: method, path, status, response time in ms
        log_line = f"{request.method} {request.path} {response.status_code} {duration_ms}ms"
        print(log_line) # Print to console
        logger.info(log_line) # Also write to logging system
        
        return response
