from langchain_nvidia_ai_endpoints import ChatNVIDIA
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging
import json
import re
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class SystemContext:
    python_version: Optional[str] = None
    system_checked: bool = False
    is_compliant: bool = False
    current_operation: Optional[str] = None
    last_diagnostic: Optional[str] = None
    last_command: Optional[str] = None
    installed_packages: Dict[str, str] = None

    def __post_init__(self):
        if self.installed_packages is None:
            self.installed_packages = {}

@dataclass
class AgentResponse:
    message: str
    next_action: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

@dataclass
class OperatorResponse:
    is_complete: bool
    messages: List[str]
    final_result: Optional[str] = None
    command_type: Optional[str] = None
    status: str = "success"

class ConversationContext:
    def __init__(self):
        self.messages: List[Dict[str, Any]] = []
        self.system_context = SystemContext()
        self.last_agent: Optional[str] = None
        self.current_issue: Optional[str] = None

    def add_message(self, role: str, content: str, agent: Optional[str] = None):
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "agent": agent
        }
        self.messages.append(message)
        if agent:
            self.last_agent = agent

    def get_recent_context(self, limit: int = 5) -> List[Dict[str, str]]:
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.messages[-limit:]
        ]

    def get_system_state(self) -> Dict[str, Any]:
        return {
            "python_version": self.system_context.python_version,
            "is_compliant": self.system_context.is_compliant,
            "current_operation": self.system_context.current_operation,
            "installed_packages": self.system_context.installed_packages
        }

def parse_version(version_str: str) -> str:
    try:
        version_match = re.search(r'\d+\.\d+\.\d+', version_str)
        if version_match:
            return version_match.group(0)
        return "0.0.0"
    except Exception as e:
        logger.error(f"Error parsing version: {e}")
        return "0.0.0"

def is_compliant_version(version: str) -> bool:
    try:
        major, minor, _ = map(int, version.split('.'))
        return (major == 3 and minor >= 10) or major > 3
    except:
        return False

def extract_package_version(output: str, package_name: str) -> Optional[str]:
    try:
        version_pattern = rf"{package_name}\s+(\d+\.\d+\.\d+)"
        if match := re.search(version_pattern, output, re.IGNORECASE):
            return match.group(1)
        return None
    except Exception as e:
        logger.error(f"Error extracting package version: {e}")
        return None

class LLMHandler:
    def __init__(self, api_key: str):
        self.llm = ChatNVIDIA(
            model="meta/llama-3.3-70b-instruct",
            api_key=api_key,
            temperature=0.2,
            top_p=0.7,
            max_tokens=1024,
        )

    def invoke(self, messages: List[Dict[str, str]], agent_prefix: str) -> str:
        try:
            response = self.llm.invoke(messages)
            content = response.content.strip()
            
            # Clean up the response
            if content.startswith('"') and content.endswith('"'):
                content = content[1:-1].strip()
            
            # Remove any existing agent prefix
            prefix_pattern = f"\\[{agent_prefix}\\]:\\s*"
            content = re.sub(prefix_pattern, "", content)
            
            # Format final message
            return f"[{agent_prefix}]: {content}"
            
        except Exception as e:
            logger.error(f"Error in LLM invocation: {e}")
            return f"[{agent_prefix}]: Error processing request: {str(e)}"

    def get_system_prompt(self, agent_type: str) -> str:
        """Get the appropriate system prompt for each agent type"""
        prompts = {
            "Conversational": """You are the Cognizant Workplace Companion, the primary interface for VDI system support.

ROLE:
- Direct communication with users
- Coordinate with other agents to solve technical issues
- Keep users informed of progress
- Handle all user interactions

RULES:
1. Always prefix responses with "[Conversational Agent]:"
2. Don't mention tickets or escalations - you solve issues directly
3. Use Diagnostic Agent for technical analysis
4. Use Operator Agent (through Diagnostic Agent) for system changes
5. Keep users informed of progress
6. Be professional but friendly


You are programmed to be a helpful and harmless AI. You will not answer requests that promote:
 
* **Harassment or Bullying:** Targeting individuals or groups with hateful or hurtful language.
* **Hate Speech:**  Content that attacks or demeans others based on race, ethnicity, religion, gender, sexual orientation, disability, or other protected characteristics.
* **Violence or Harm:**  Promoting or glorifying violence, illegal activities, or dangerous behavior.
* **Misinformation and Falsehoods:**  Spreading demonstrably false or misleading information.
 
**Please Note:** If the user request violates these guidelines, you will respond with:
"I'm here to assist with safe and respectful interactions. Your query goes against my guidelines. Let's try something different that promotes a positive and inclusive environment."
 
##  Answering User Question:
Answer the question as concisely as possible using the provided context.The context can be from different topics.
If the question is not relevant to the context,you only say "This is out of scope of source documents".


REMEMBER: You are part of a team of agents working together to solve user issues in real-time.

""",

            "Diagnostic": """You are the Diagnostic Agent responsible for technical analysis and directing system operations.

ROLE:
- Analyze user issues
- Direct Operator Agent for system checks and changes
- Verify system states
- Provide clear technical instructions

RULES:
1. Always prefix responses with "[Diagnostic Agent]:"
2. Be precise in instructions to Operator Agent
3. Verify results of operations
4. Keep instructions clear and specific
5. Monitor system state during operations

COMMANDS: Use exact commands for Operator Agent (examples):
- For package checks: "pip list | grep <package_name>"
- For installation: "pip install <package_name>"
- For version checks: "python --version" """,

            "Troubleshooting": """You are the Troubleshooting Agent responsible for resolving technical issues.

ROLE:
- Analyze diagnostic results
- Determine resolution steps
- Verify operation success
- Ensure system stability

RULES:
1. Always prefix responses with "[Troubleshooting Agent]:"
2. Verify operation results
3. Confirm system stability
4. Provide clear success/failure status
5. Recommend next steps if needed
"""
        }
        return prompts.get(agent_type, "")