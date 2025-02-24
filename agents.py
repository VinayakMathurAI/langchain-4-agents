from typing import Callable, Awaitable, Dict, Any, List, Optional
import logging
from base import LLMHandler, ConversationContext, parse_version, is_compliant_version
from tools import OperatorAgentTool, DiagnosticTool, TroubleshootingTool

logger = logging.getLogger(__name__)

class ConversationalAgent:
    def __init__(self, message_callback: Callable[[str], Awaitable[None]]):
        api_key = "enter your key"
        
        self.llm_handler = LLMHandler(api_key)
        self.message_callback = message_callback
        self.operator_tool = OperatorAgentTool(message_callback)
        self.diagnostic_tool = DiagnosticTool(self.operator_tool, self.llm_handler)
        self.troubleshooting_tool = TroubleshootingTool(self.llm_handler)
        
        self.context = ConversationContext()
        self.system_prompt = self.llm_handler.get_system_prompt("Conversational")

    async def send_message(self, message: str):
        await self.message_callback(message)

    async def get_response(self, user_message: str):
        logger.info(f"Processing user message: {user_message}")
        
        try:
            # Store user message in context
            self.context.add_message("user", user_message)

            # Initial compliance check if not done
            if not self.context.system_context.system_checked:
                await self._run_compliance_check()
                return

            # If system is not compliant, handle compliance issues
            if not self.context.system_context.is_compliant:
                await self._handle_compliance_issues()
                return

            # Process user query
            await self._process_user_query(user_message)

        except Exception as e:
            logger.error(f"Error in get_response: {str(e)}")
            await self.send_message(
                "[Conversational Agent]: I apologize, but I encountered an error. "
                "Let me analyze the issue and try again."
            )

    async def _run_compliance_check(self):
        try:
            # Start with Diagnostic Agent
            diagnostic_response = await self.diagnostic_tool.analyze("initial_check", self.context)
            await self.send_message(diagnostic_response.message)

            # Get Operator Agent to check Python version
            operator_response = await self.operator_tool.execute("python --version", self.context)
            if operator_response.is_complete:
                version = parse_version(operator_response.final_result)
                self.context.system_context.python_version = version
                
                # Pass to Troubleshooting Agent for analysis
                troubleshooting_response = await self.troubleshooting_tool.analyze(
                    {"python_version": version},
                    self.context
                )
                await self.send_message(troubleshooting_response.message)

                # Update system status
                self.context.system_context.system_checked = True
                self.context.system_context.is_compliant = is_compliant_version(version)

                if self.context.system_context.is_compliant:
                    await self.send_message(
                        "[Conversational Agent]: System compliance check is complete. How may I assist you today?"
                    )
                else:
                    await self.send_message(
                        "[Conversational Agent]: I've detected that your system needs updates. "
                        "I'll help resolve these compliance issues first."
                    )

        except Exception as e:
            logger.error(f"Error in compliance check: {e}")
            await self.send_message(
                "[Conversational Agent]: I encountered an issue during the system check. "
                "Let me try to resolve this."
            )

    async def _process_user_query(self, user_message: str):
        # Check if it's a software installation request
        if any(keyword in user_message.lower() for keyword in ["install", "update", "upgrade"]):
            await self._handle_installation_request(user_message)
            return

        # Check for system issues
        if any(keyword in user_message.lower() for keyword in 
            ["slow", "error", "issue", "problem", "not working", "failed", "crash", "performance"]):
            await self._handle_system_issue(user_message)
            return

        # General query handling
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        # Add relevant context
        messages.extend(self.context.get_recent_context())
        
        response = self.llm_handler.invoke(messages, "Conversational Agent")
        await self.send_message(response)

    async def _handle_installation_request(self, user_message: str):
        # Let user know we're processing their request
        await self.send_message(
            "[Conversational Agent]: I'll help you with the installation. "
            "Let me check the requirements first."
        )

        # Get Diagnostic Agent to analyze the request
        diagnostic_response = await self.diagnostic_tool.analyze(user_message, self.context)
        await self.send_message(diagnostic_response.message)

        if diagnostic_response.next_action == "install_package":
            # Get Operator to perform installation
            operator_response = await self.operator_tool.execute(
                f"pip install {diagnostic_response.data['package']}", 
                self.context
            )

            if operator_response.is_complete:
                # Verify installation
                troubleshooting_response = await self.troubleshooting_tool.analyze(
                    {"package": diagnostic_response.data['package'], "status": "installed"},
                    self.context
                )
                await self.send_message(troubleshooting_response.message)

                # Confirm to user
                await self.send_message(
                    f"[Conversational Agent]: The installation is complete. "
                    f"Is there anything else you need assistance with?"
                )

    async def _handle_system_issue(self, user_message: str):
        await self.send_message(
            "[Conversational Agent]: I'll help diagnose and resolve this issue. "
            "Let me analyze your system."
        )

        # Get Diagnostic Agent to analyze
        diagnostic_response = await self.diagnostic_tool.analyze(user_message, self.context)
        await self.send_message(diagnostic_response.message)

        # Get Operator to check system
        operator_response = await self.operator_tool.execute(
            diagnostic_response.next_action,
            self.context
        )

        if operator_response.is_complete:
            # Get Troubleshooting to analyze
            troubleshooting_response = await self.troubleshooting_tool.analyze(
                {"issue_type": "system_issue", "diagnostic_data": operator_response.final_result},
                self.context
            )
            await self.send_message(troubleshooting_response.message)

            # Provide update to user
            await self.send_message(
                "[Conversational Agent]: I've analyzed the issue. "
                "Would you like me to proceed with the recommended solution?"
            )

    async def _handle_compliance_issues(self):
        if not self.context.system_context.python_version:
            await self.send_message(
                "[Conversational Agent]: I need to verify your system's Python version again."
            )
            await self._run_compliance_check()
            return

        await self.send_message(
            "[Conversational Agent]: I'm working on resolving the compliance issues. "
            "This may take a few moments."
        )

        # Get Diagnostic Agent to analyze compliance issue
        diagnostic_response = await self.diagnostic_tool.analyze(
            "resolve_compliance",
            self.context
        )
        await self.send_message(diagnostic_response.message)

        # Execute resolution steps
        operator_response = await self.operator_tool.execute(
            diagnostic_response.next_action,
            self.context
        )

        if operator_response.is_complete:
            # Verify resolution
            verification_response = await self.operator_tool.execute(
                "python --version",
                self.context
            )
            
            if verification_response.is_complete:
                version = parse_version(verification_response.final_result)
                if is_compliant_version(version):
                    self.context.system_context.is_compliant = True
                    await self.send_message(
                        "[Conversational Agent]: System compliance has been restored. "
                        "How may I assist you?"
                    )
                else:
                    await self.send_message(
                        "[Conversational Agent]: I'm still working on resolving the compliance issues. "
                        "Please bear with me."
                    )
