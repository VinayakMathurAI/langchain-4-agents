from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import json
import asyncio
import logging
from agents import ConversationalAgent
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Store active connections and their agents
connections = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up FastAPI server...")
    yield
    logger.info("Shutting down FastAPI server...")
    # Clean up connections
    for connection in list(connections.keys()):
        try:
            await connection.close()
        except:
            logger.error(f"Error closing connection during shutdown")
    connections.clear()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def validate_message(message: str, agent_prefix: str) -> str:
    """Ensure message has proper agent prefix and formatting"""
    valid_prefixes = [
        "[Conversational Agent]:",
        "[Diagnostic Agent]:",
        "[Troubleshooting Agent]:",
        "[Operator Agent]:"
    ]
    
    if not any(message.startswith(prefix) for prefix in valid_prefixes):
        if agent_prefix:
            return f"[{agent_prefix}]: {message}"
        return f"[System]: {message}"
    return message

async def send_message_to_client(websocket: WebSocket, message: str, agent_prefix: str = None):
    """Send formatted message to client with error handling"""
    try:
        formatted_message = await validate_message(message, agent_prefix)
        logger.info(f"Sending message: {formatted_message}")
        
        await websocket.send_json({
            "type": "message",
            "content": {
                "type": "text",
                "text": formatted_message
            }
        })
        await asyncio.sleep(0.5)  # Delay for message readability
        
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        try:
            error_message = f"[System Error]: Failed to send message - {str(e)}"
            await websocket.send_json({
                "type": "error",
                "content": {
                    "type": "text",
                    "text": error_message
                }
            })
        except:
            logger.error("Failed to send error message")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("New WebSocket connection accepted")
    
    async def message_callback(message: str):
        await send_message_to_client(websocket, message)
    
    try:
        # Initialize agent
        agent = ConversationalAgent(message_callback)
        connections[websocket] = {
            'agent': agent,
            'active': True,
            'messages_processed': 0
        }
        
        while connections[websocket]['active']:
            try:
                # Receive and validate message
                data = await websocket.receive_text()
                logger.info(f"Received message: {data}")
                
                # Parse message
                try:
                    message_data = json.loads(data)
                    user_message = message_data.get("message", "").strip()
                    
                    if not user_message:
                        logger.warning("Received empty message")
                        continue
                    
                    # Process message
                    connections[websocket]['messages_processed'] += 1
                    logger.info(f"Processing message #{connections[websocket]['messages_processed']}")
                    
                    await agent.get_response(user_message)
                    
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                    await send_message_to_client(
                        websocket,
                        "I couldn't process that message. Please try again with a valid format.",
                        "Conversational Agent"
                    )
                    
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected")
                break
                
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                await send_message_to_client(
                    websocket,
                    f"I encountered an error while processing your message: {str(e)}",
                    "Conversational Agent"
                )
                
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
        try:
            await send_message_to_client(
                websocket,
                "Connection error occurred. Please refresh the page and try again.",
                "System"
            )
        except:
            logger.error("Failed to send final error message")
            
    finally:
        # Clean up connection
        if websocket in connections:
            logger.info(f"Cleaning up connection. Processed {connections[websocket]['messages_processed']} messages.")
            connections[websocket]['active'] = False
            del connections[websocket]
        try:
            await websocket.close()
        except:
            logger.error("Error closing websocket")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "active_connections": len(connections),
        "uptime": "available"
    }

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting FastAPI server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)