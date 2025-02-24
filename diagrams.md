Here's a comprehensive architecture diagram using Mermaid code. I'll break it down into several connected diagrams for better clarity:

```mermaid
graph TB
    subgraph "Client Layer"
        UI[React Chat Interface]
        WS[WebSocket Client]
        Voice[Voice Input/Output]
        UI --> WS
        UI --> Voice
    end

    subgraph "Server Layer"
        FAPI[FastAPI Server :8000]
        WH[WebSocket Handler]
        CM[Connection Manager]
        FAPI --> WH
        WH --> CM
    end

    subgraph "Agent Layer"
        CA[Conversational Agent]
        DT[Diagnostic Tool]
        TT[Troubleshooting Tool]
        OT[Operator Tool]
        
        CA --> DT
        CA --> TT
        DT --> OT
        TT --> OT
    end

    subgraph "External Services"
        NVAI[NVIDIA AI LLM]
        OP[Operator Agent :8501]
    end

    WS --> FAPI
    CA --> NVAI
    OT --> OP

```

And here's a more detailed flow diagram:

```mermaid
flowchart TD
    subgraph "Message Flow"
        A[Client Message] --> B[WebSocket Handler]
        B --> C{Conversational Agent}
        
        C -->|First Message| D[System Check]
        C -->|Install Request| E[Package Management]
        C -->|General Query| F[LLM Processing]
        
        D --> G[Diagnostic Tool]
        E --> G
        F --> C
        
        G --> H{Analysis Type}
        H -->|Version Check| I[Python Version Verification]
        H -->|Package Check| J[Package Status Check]
        H -->|System Issue| K[System Diagnostics]
        
        I --> L[Troubleshooting Tool]
        J --> L
        K --> L
        
        L --> M{Resolution Type}
        M -->|Compliance Issue| N[System Update]
        M -->|Package Issue| O[Package Installation]
        M -->|General Issue| P[Issue Resolution]
        
        N --> Q[Operator Tool]
        O --> Q
        P --> Q
        
        Q --> R[Operator Agent]
        R --> S[System Changes]
        
        S --> T[Result Processing]
        T --> C
        
        C --> U[Client Response]
    end
```

And here's the context and state management diagram:

```mermaid
classDiagram
    class ConversationContext {
        +List messages
        +SystemContext system_context
        +String last_agent
        +add_message()
        +get_recent_context()
        +get_system_state()
    }
    
    class SystemContext {
        +String python_version
        +Bool system_checked
        +Bool is_compliant
        +String current_operation
        +Dict installed_packages
    }
    
    class AgentResponse {
        +String message
        +String next_action
        +Dict data
    }
    
    class OperatorResponse {
        +Bool is_complete
        +List messages
        +String final_result
        +String command_type
        +String status
    }
    
    ConversationContext --> SystemContext
    ConversationalAgent --> ConversationContext
    ConversationalAgent --> AgentResponse
    OperatorTool --> OperatorResponse
```

And finally, the component interaction diagram:

```mermaid
sequenceDiagram
    participant Client
    participant WebSocket
    participant ConversationalAgent
    participant DiagnosticTool
    participant TroubleshootingTool
    participant OperatorTool
    participant OperatorAgent
    participant NVIDIA_LLM

    Client->>WebSocket: Connect()
    WebSocket->>ConversationalAgent: Initialize()
    
    Client->>WebSocket: Send Message
    WebSocket->>ConversationalAgent: Process Message
    
    alt First Message
        ConversationalAgent->>DiagnosticTool: Check System
        DiagnosticTool->>OperatorTool: Version Check
        OperatorTool->>OperatorAgent: Execute Command
        OperatorAgent-->>OperatorTool: Result
        OperatorTool-->>DiagnosticTool: Version Info
        DiagnosticTool->>TroubleshootingTool: Analyze
        TroubleshootingTool-->>ConversationalAgent: Compliance Status
    else Installation Request
        ConversationalAgent->>DiagnosticTool: Analyze Request
        DiagnosticTool->>OperatorTool: Check Package
        OperatorTool->>OperatorAgent: Execute Command
        OperatorAgent-->>OperatorTool: Package Status
        OperatorTool-->>DiagnosticTool: Status Info
        DiagnosticTool->>TroubleshootingTool: Verify
        TroubleshootingTool-->>ConversationalAgent: Installation Status
    else General Query
        ConversationalAgent->>NVIDIA_LLM: Process Query
        NVIDIA_LLM-->>ConversationalAgent: Response
    end
    
    ConversationalAgent-->>WebSocket: Send Response
    WebSocket-->>Client: Display Response
```

This set of diagrams provides a comprehensive view of:
1. Overall system architecture
2. Detailed message flow
3. Context and state management
4. Component interactions
5. Sequence of operations

Each diagram highlights different aspects of the system:
- First diagram: System components and their relationships
- Second diagram: Detailed message processing flow
- Third diagram: Data structure relationships
- Fourth diagram: Temporal sequence of interactions

These diagrams can be rendered using any Mermaid-compatible markdown viewer or editor.