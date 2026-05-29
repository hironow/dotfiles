import os
import logging
import time
import random
from typing import Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
import httpx
import uvicorn

from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry._logs import set_logger_provider

# Configure OpenTelemetry
def configure_opentelemetry():
    # Create resource
    resource = Resource.create({
        "service.name": "fastapi-example",
        "service.version": "1.0.0",
        "deployment.environment": "development"
    })
    
    # Configure tracing
    trace_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(trace_provider)
    
    otlp_exporter = OTLPSpanExporter(
        endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317"),
        insecure=True
    )
    span_processor = BatchSpanProcessor(otlp_exporter)
    trace_provider.add_span_processor(span_processor)
    
    # Configure metrics
    metric_reader = PeriodicExportingMetricReader(
        exporter=OTLPMetricExporter(
            endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317"),
            insecure=True
        ),
        export_interval_millis=10000
    )
    metrics_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(metrics_provider)
    
    # Configure logging
    logger_provider = LoggerProvider(resource=resource)
    set_logger_provider(logger_provider)
    
    log_exporter = OTLPLogExporter(
        endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317"),
        insecure=True
    )
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    
    # Add OTLP handler to root logger
    handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    logging.getLogger().addHandler(handler)
    
    return trace_provider, metrics_provider

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OpenTelemetry
trace_provider, metrics_provider = configure_opentelemetry()
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Create metrics
request_counter = meter.create_counter(
    name="http_requests_total",
    description="Total number of HTTP requests",
    unit="1"
)

request_duration_histogram = meter.create_histogram(
    name="http_request_duration_seconds",
    description="HTTP request duration",
    unit="s"
)

active_requests = meter.create_up_down_counter(
    name="http_requests_active",
    description="Number of active HTTP requests",
    unit="1"
)

# Instrument libraries
LoggingInstrumentor().instrument(set_logging_format=True)
HTTPXClientInstrumentor().instrument()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("FastAPI application starting up")
    yield
    # Shutdown
    logger.info("FastAPI application shutting down")

# Create FastAPI app
app = FastAPI(title="OpenTelemetry Example API", lifespan=lifespan)

# Instrument FastAPI
FastAPIInstrumentor.instrument_app(app)

@app.get("/")
async def root():
    logger.info("Root endpoint called")
    request_counter.add(1, {"endpoint": "/", "method": "GET"})
    return {"message": "Hello from OpenTelemetry instrumented FastAPI!"}

@app.get("/api/users/{user_id}")
async def get_user(user_id: int):
    with tracer.start_as_current_span("get_user") as span:
        span.set_attribute("user.id", user_id)
        logger.info(f"Fetching user {user_id}")
        
        # Simulate some processing time
        processing_time = random.uniform(0.1, 0.5)
        time.sleep(processing_time)
        
        # Record metrics
        request_counter.add(1, {"endpoint": "/api/users", "method": "GET"})
        request_duration_histogram.record(processing_time, {"endpoint": "/api/users"})
        
        if user_id == 999:
            logger.error(f"User {user_id} not found")
            raise HTTPException(status_code=404, detail="User not found")
        
        user_data = {
            "id": user_id,
            "name": f"User {user_id}",
            "email": f"user{user_id}@example.com"
        }
        
        logger.info(f"Successfully retrieved user {user_id}")
        return user_data

@app.post("/api/orders")
async def create_order(order: Dict):
    with tracer.start_as_current_span("create_order") as span:
        order_id = random.randint(1000, 9999)
        span.set_attribute("order.id", order_id)
        span.set_attribute("order.items_count", len(order.get("items", [])))
        
        logger.info(f"Creating order {order_id}")
        active_requests.add(1, {"endpoint": "/api/orders"})
        
        try:
            # Simulate order processing
            processing_time = random.uniform(0.2, 1.0)
            time.sleep(processing_time)
            
            # Record metrics
            request_counter.add(1, {"endpoint": "/api/orders", "method": "POST"})
            request_duration_histogram.record(processing_time, {"endpoint": "/api/orders"})
            
            # Simulate external API call
            with tracer.start_as_current_span("external_api_call"):
                logger.info("Making external API call for order validation")
                # Simulate API call
                time.sleep(0.1)
            
            order_response = {
                "id": order_id,
                "status": "created",
                "items": order.get("items", []),
                "total": sum(item.get("price", 0) for item in order.get("items", []))
            }
            
            logger.info(f"Order {order_id} created successfully")
            return order_response
            
        except Exception as e:
            logger.error(f"Error creating order: {str(e)}")
            raise HTTPException(status_code=500, detail="Error creating order")
        finally:
            active_requests.add(-1, {"endpoint": "/api/orders"})

@app.get("/api/external")
async def call_external_service():
    with tracer.start_as_current_span("call_external") as span:
        logger.info("Calling external service")
        
        try:
            async with httpx.AsyncClient() as client:
                # This will also be traced thanks to instrumentation
                response = await client.get("https://httpbin.org/json")
                
            logger.info("External service call successful")
            request_counter.add(1, {"endpoint": "/api/external", "method": "GET"})
            
            return {
                "status": "success",
                "external_data": response.json()
            }
        except Exception as e:
            logger.error(f"External service call failed: {str(e)}")
            span.record_exception(e)
            raise HTTPException(status_code=502, detail="External service error")

@app.get("/api/slow")
async def slow_operation():
    with tracer.start_as_current_span("slow_operation") as span:
        logger.info("Starting slow operation")
        
        # Simulate a slow operation with multiple steps
        for i in range(5):
            with tracer.start_as_current_span(f"step_{i+1}"):
                step_duration = random.uniform(0.1, 0.3)
                logger.info(f"Processing step {i+1}")
                time.sleep(step_duration)
                span.set_attribute(f"step.{i+1}.duration", step_duration)
        
        logger.info("Slow operation completed")
        request_counter.add(1, {"endpoint": "/api/slow", "method": "GET"})
        
        return {"status": "completed", "steps": 5}

@app.get("/health")
async def health_check():
    logger.debug("Health check called")
    return {"status": "healthy", "service": "fastapi-example"}

if __name__ == "__main__":
    logger.info("Starting FastAPI application with OpenTelemetry instrumentation")
    uvicorn.run(app, host="0.0.0.0", port=8000)