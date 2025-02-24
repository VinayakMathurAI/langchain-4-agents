from typing import Callable, Awaitable, Dict, Any, List, Optional
import websockets
import json
import logging
import asyncio
import re
from base import OperatorResponse, AgentResponse, LLMHandler, ConversationContext, extract_package_version, parse_version

logger = logging.getLogger(__name__)

class OperatorAgentTool:
    def __init__(self, message_callback: Callable[[str], Awaitable[None]]):
        self.ws_url = "ws://localhost:8501/ws"
        self.message_callback = message_callback

    async def execute(self, command: str, context: ConversationContext) -> OperatorResponse:
        logger.info(f"Operator Agent executing command: {command}")
        command_type = self._determine_command_type(command)
        
        try:
            async with websockets.connect(self.ws_url) as websocket:
                await websocket.send(json.dumps({"message": command}))
                
                messages = []
                response_received = False
                timeout = 30  # 30 seconds timeout
                start_time = asyncio.get_event_loop().time()
                
                while not response_received and len(messages) < 10:  # Increased max messages
                    try:
                        # Add timeout to websocket.recv()
                        response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                        response_data = json.loads(response)
                        
                        if response_data["type"] == "message":
                            message = response_data['content'].get('text', '')
                            if message:
                                formatted_message = self._format_operator_message(message)
                                if formatted_message not in messages:
                                    messages.append(formatted_message)
                                    await self.message_callback(formatted_message)
                                    
                                    # For installation commands, look for specific completion indicators
                                    if command_type == "installation":
                                        if any(x in formatted_message.lower() for x in [
                                            "installed", 
                                            "successfully",
                                            "requirement already satisfied",
                                            "error:",
                                            "failed"
                                        ]):
                                            response_received = True
                                            break
                                    else:
                                        # For other commands, use normal completion check
                                        if self._is_command_complete(formatted_message, command_type):
                                            response_received = True
                                            break
                        
                        # Check for timeout
                        if asyncio.get_event_loop().time() - start_time > timeout:
                            logger.warning("Operation timed out")
                            break
                            
                    except asyncio.TimeoutError:
                        logger.warning("Timeout waiting for response")
                        break

                # If we have messages but didn't get a completion signal, use the last message
                final_message = messages[-1] if messages else "No response received"
                
                # Special handling for installation completion
                if command_type == "installation" and not response_received:
                    # Check if we have enough information to determine success
                    install_success = any("installed" in msg.lower() for msg in messages)
                    install_error = any("error" in msg.lower() for msg in messages)
                    
                    if install_success or install_error:
                        response_received = True

                return OperatorResponse(
                    is_complete=True,  # Always return complete to prevent hanging
                    messages=messages,
                    final_result=final_message,
                    command_type=command_type,
                    status="success" if response_received else "incomplete"
                )

        except Exception as e:
            logger.error(f"Error in operator execution: {str(e)}")
            error_message = f"[Operator Agent]: Error - {str(e)}"
            return OperatorResponse(
                is_complete=True,
                messages=[error_message],
                final_result=error_message,
                command_type=command_type,
                status="error"
            )

    def _determine_command_type(self, command: str) -> str:
        if "pip install" in command:
            return "installation"
        elif "pip list" in command or "grep" in command:
            return "package_check"
        elif "python --version" in command:
            return "version_check"
        return "general"

    def _format_operator_message(self, message: str) -> str:
        if not message.startswith("[Operator Agent]:"):
            message = f"[Operator Agent]: {message}"
        return message.replace("Operator Agent\n", "").strip()

    def _update_context(self, context: ConversationContext, command_type: str, message: str):
        message_lower = message.lower()
        if command_type == "version_check" and "python" in message_lower:
            version = parse_version(message)
            context.system_context.python_version = version
        elif command_type == "package_check":
            if "not installed" in message_lower or "not found" in message_lower:
                # Handle package not found case
                package_name = message.split(":")[-1].strip().lower().replace("is not installed", "").strip()
                context.system_context.installed_packages[package_name] = None
            elif match := re.search(r'(\w+)\s+version:\s*([\d\.]+)', message, re.IGNORECASE):
                # Handle found package case
                package_name, version = match.groups()
                context.system_context.installed_packages[package_name.lower()] = version
        elif command_type == "installation" and any(x in message_lower for x in ["installed", "successfully"]):
            # Extract package and version information from installation message
            if match := re.search(r'installed\s+(\w+)\s*(?:version\s*)?([\d\.]+)?', message_lower):
                package_name, version = match.groups()
                if version:
                    context.system_context.installed_packages[package_name] = version
        
        context.system_context.last_command = command_type
        context.add_message("system", message, "Operator Agent")

    def _is_command_complete(self, message: str, command_type: str) -> bool:
        message_lower = message.lower()
        if command_type == "installation":
            return any(x in message_lower for x in [
                "successfully installed",
                "requirement already satisfied",
                "installed",
                "error:",
                "failed",
                "installation complete"
            ])
        elif command_type == "version_check":
            return any(x in message_lower for x in ["python version", "version:"])
        elif command_type == "package_check":
            return any(x in message_lower for x in [
                "found",
                "not found",
                "version",
                "is not installed",
                "result:",
                "not installed in this environment",
                "error:"
            ])
        return True

class DiagnosticTool:
    def __init__(self, operator_tool: OperatorAgentTool, llm_handler: LLMHandler):
        self.operator_tool = operator_tool
        self.llm_handler = llm_handler
        self.system_prompt = self.llm_handler.get_system_prompt("Diagnostic")

    async def analyze(self, context: str, conversation_context: ConversationContext) -> AgentResponse:
        if "install" in context.lower():
            package_name = self._extract_package_name(context)
            if package_name:
                return await self._handle_package_installation(package_name, conversation_context)
        
        if "initial_check" in context:
            return AgentResponse(
                message="[Diagnostic Agent]: Initiating automatic system compliance check. Operator Agent will verify Python version requirements.",
                next_action="check_python",
                data={"type": "compliance_check"}
            )

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Analyze this issue and provide specific diagnostic steps: {context}"}
        ]
        
        response = self.llm_handler.invoke(messages, "Diagnostic Agent")
        return AgentResponse(
            message=response,
            next_action="analyze_issue",
            data={"type": "general_diagnostic"}
        )

    def _extract_package_name(self, context: str) -> Optional[str]:
        packages = ["numpy", "pandas", "scipy", "matplotlib", "sklearn", "tensorflow", "torch"]
        for package in packages:
            if package in context.lower():
                return package
        return None

    async def _handle_package_installation(self, package_name: str, conversation_context: ConversationContext) -> AgentResponse:
        check_command = f"pip list | grep {package_name}"
        check_response = await self.operator_tool.execute(check_command, conversation_context)
        
        if check_response.final_result and any(x in check_response.final_result.lower() for x in 
            ["not installed", "not found", "is not installed in this environment"]):
            return AgentResponse(
                message=f"[Diagnostic Agent]: Package {package_name} is not installed. Initiating installation process.",
                next_action="install_package",
                data={"package": package_name, "action": "install"}
            )
        elif check_response.final_result and package_name.lower() in check_response.final_result.lower():
            version = extract_package_version(check_response.final_result, package_name)
            return AgentResponse(
                message=f"[Diagnostic Agent]: Package {package_name} is already installed (version {version}). No action needed.",
                next_action="none",
                data={"package": package_name, "version": version, "status": "installed"}
            )
        else:
            return AgentResponse(
                message=f"[Diagnostic Agent]: Unable to verify {package_name} status. Proceeding with installation attempt.",
                next_action="install_package",
                data={"package": package_name, "action": "install"}
            )

class TroubleshootingTool:
    def __init__(self, llm_handler: LLMHandler):
        self.llm_handler = llm_handler
        self.system_prompt = self.llm_handler.get_system_prompt("Troubleshooting")

    async def analyze(self, diagnostic_data: Dict[str, Any], conversation_context: ConversationContext) -> AgentResponse:
        if "package" in diagnostic_data:
            return self._analyze_package_operation(diagnostic_data, conversation_context)
        
        if "python_version" in diagnostic_data:
            return self._analyze_python_version(diagnostic_data["python_version"])
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Analyze this diagnostic data and provide resolution steps: {json.dumps(diagnostic_data)}"}
        ]
        
        response = self.llm_handler.invoke(messages, "Troubleshooting Agent")
        return AgentResponse(
            message=response,
            next_action="analyze_further",
            data={"status": "needs_investigation"}
        )

    def _analyze_package_operation(self, data: Dict[str, Any], context: ConversationContext) -> AgentResponse:
        package_name = data["package"]
        if "action" in data and data["action"] == "install":
            return AgentResponse(
                message=f"[Troubleshooting Agent]: Installation of {package_name} will proceed. Monitoring installation process.",
                next_action="monitor_installation",
                data={"package": package_name}
            )
        elif "status" in data and data["status"] == "installed":
            return AgentResponse(
                message=f"[Troubleshooting Agent]: {package_name} is already installed and functioning. No remediation needed.",
                next_action="none",
                data={"status": "verified"}
            )
        return AgentResponse(
            message=f"[Troubleshooting Agent]: Unable to verify {package_name} status. Further investigation needed.",
            next_action="investigate",
            data={"status": "unknown"}
        )

    def _analyze_python_version(self, version: str) -> AgentResponse:
        if parse_version(version) >= "3.10":
            return AgentResponse(
                message=f"[Troubleshooting Agent]: Python {version} meets minimum requirement of 3.10. No remediation needed.",
                next_action="proceed",
                data={"status": "compliant"}
            )
        return AgentResponse(
            message=f"[Troubleshooting Agent]: Python {version} does not meet minimum requirement of 3.10. Remediation required.",
                next_action="uninstall_python",
                data={"status": "non_compliant"}
            )