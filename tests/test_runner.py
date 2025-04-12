#!/usr/bin/env python
"""
WhatsApp Invoice Assistant Test Runner

This script provides utilities for running tests and interactive testing
of the WhatsApp Invoice Assistant components.

Usage:
  python test_runner.py --all                 # Run all tests
  python test_runner.py --agent entity        # Run all entity extraction tests
  python test_runner.py --interactive         # Start interactive testing mode
  python test_runner.py --specific test_file.py::test_function  # Run a specific test
"""

import os
import sys
from pathlib import Path

# Add the project root directory to Python path
project_root = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(project_root))

import argparse
import logging
import pytest
import asyncio
import json
from typing import Dict, Any, List, Optional, Union

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("test_runner")

# Import required agent classes for interactive testing
try:
    from services.llm_factory import LLMFactory
    from agents.text_intent_classifier import TextIntentClassifierAgent
    from agents.invoice_entity_extraction_agent import InvoiceEntityExtractionAgent
    from agents.text_to_sql_conversion_agent import TextToSQLConversionAgent
    from agents.response_formatter import ResponseFormatterAgent
    from agents.file_validator import FileValidatorAgent
    from agents.data_extractor import DataExtractorAgent
    from utils.base_agent import AgentInput, AgentContext
    
    # Flag to indicate if agent imports were successful
    AGENTS_IMPORTED = True
except ImportError as e:
    logger.warning(f"Failed to import agent classes: {e}")
    logger.warning("Interactive mode will be limited to running tests only.")
    AGENTS_IMPORTED = False


# Test directory paths
BASE_TEST_DIR = Path("tests")
AGENT_TEST_DIR = BASE_TEST_DIR / "agents"
SERVICE_TEST_DIR = BASE_TEST_DIR / "services"
DATABASE_TEST_DIR = BASE_TEST_DIR / "database"
WORKFLOW_TEST_DIR = BASE_TEST_DIR / "langchain_app"


def run_all_tests() -> int:
    """
    Run all tests in the project.
    
    Returns:
        int: Exit code (0 for success, non-zero for failure)
    """
    logger.info("Running all tests...")
    return pytest.main(["-xvs", str(BASE_TEST_DIR)])


def run_agent_tests(agent_name: Optional[str] = None) -> int:
    """
    Run tests for a specific agent or all agents.
    
    Args:
        agent_name: Name of the agent to test (or None for all agents)
        
    Returns:
        int: Exit code (0 for success, non-zero for failure)
    """
    if agent_name:
        # Map common agent name variations to their test file
        agent_map = {
            "intent": "test_text_intent_classifier.py",
            "entity": "test_entity_extraction.py",
            "sql": "test_text_to_sql_conversion.py",
            "format": "test_response_formatter.py",
            "validator": "test_file_validator.py",
            "extractor": "test_data_extractor.py",
        }
        
        # Get the test file name from the map, or use the agent name directly
        test_file = agent_map.get(agent_name.lower(), f"test_{agent_name}.py")
        test_path = AGENT_TEST_DIR / test_file
        
        if not test_path.exists():
            logger.error(f"Test file not found: {test_path}")
            return 1
            
        logger.info(f"Running tests for agent: {agent_name}")
        return pytest.main(["-xvs", str(test_path)])
    else:
        logger.info("Running all agent tests...")
        return pytest.main(["-xvs", str(AGENT_TEST_DIR)])


def run_service_tests(service_name: Optional[str] = None) -> int:
    """
    Run tests for a specific service or all services.
    
    Args:
        service_name: Name of the service to test (or None for all services)
        
    Returns:
        int: Exit code (0 for success, non-zero for failure)
    """
    if service_name:
        test_path = SERVICE_TEST_DIR / f"test_{service_name}.py"
        
        if not test_path.exists():
            logger.error(f"Test file not found: {test_path}")
            return 1
            
        logger.info(f"Running tests for service: {service_name}")
        return pytest.main(["-xvs", str(test_path)])
    else:
        logger.info("Running all service tests...")
        return pytest.main(["-xvs", str(SERVICE_TEST_DIR)])


def run_specific_test(test_path: str) -> int:
    """
    Run a specific test file or test function.
    
    Args:
        test_path: Path to the test file or file::function to run
        
    Returns:
        int: Exit code (0 for success, non-zero for failure)
    """
    logger.info(f"Running specific test: {test_path}")
    return pytest.main(["-xvs", test_path])


def get_test_status() -> Dict[str, Any]:
    """
    Get the status of all tests in the project.
    
    Returns:
        Dict containing test status information
    """
    # Use pytest to collect (but not run) all tests
    logger.info("Collecting test status...")
    collected = pytest.main(["--collect-only", "-q", str(BASE_TEST_DIR)])
    
    # Get counts of tests by directory
    agent_tests = len(list(AGENT_TEST_DIR.glob("test_*.py")))
    service_tests = len(list(SERVICE_TEST_DIR.glob("test_*.py")))
    database_tests = len(list(DATABASE_TEST_DIR.glob("test_*.py")))
    workflow_tests = len(list(WORKFLOW_TEST_DIR.glob("test_*.py")))
    
    # Count total test functions
    total_test_functions = 0
    for test_file in BASE_TEST_DIR.glob("**/*test_*.py"):
        with open(test_file, "r") as f:
            content = f.read()
            # Count functions starting with "test_" or decorated with @pytest.mark
            total_test_functions += content.count("def test_")
    
    return {
        "agent_test_files": agent_tests,
        "service_test_files": service_tests,
        "database_test_files": database_tests,
        "workflow_test_files": workflow_tests,
        "total_test_files": agent_tests + service_tests + database_tests + workflow_tests,
        "total_test_functions": total_test_functions,
        "collection_status": collected == 0
    }


class AgentTestingConsole:
    """
    Interactive console for testing agents with custom queries.
    """
    
    def __init__(self):
        """Initialize the testing console."""
        self.llm_factory = None
        self.agents = {}
        self.db_schema_info = """
        Table: invoices
        Columns:
          - id: UUID (primary key)
          - user_id: UUID (foreign key to users.id)
          - vendor: TEXT 
          - invoice_number: TEXT
          - invoice_date: DATE
          - due_date: DATE
          - total_amount: NUMERIC(10,2)
          - currency: TEXT
          - status: TEXT
          - created_at: TIMESTAMP
          - updated_at: TIMESTAMP
        
        Table: items
          - id: UUID (primary key)
          - invoice_id: UUID (foreign key to invoices.id)
          - description: TEXT
          - quantity: NUMERIC
          - unit_price: NUMERIC(10,2)
          - total_price: NUMERIC(10,2)
        """
        self.conversation_history = []
        
        # Initialize asyncio loop
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
    
    def init_agents(self):
        """Initialize all agent instances."""
        if not AGENTS_IMPORTED:
            logger.error("Agent classes could not be imported. Interactive agent testing is not available.")
            return False
            
        logger.info("Initializing LLM Factory and agents...")
        try:
            self.llm_factory = LLMFactory()
            
            # Initialize all agent instances
            self.agents = {
                "intent": TextIntentClassifierAgent(llm_factory=self.llm_factory),
                "entity": InvoiceEntityExtractionAgent(llm_factory=self.llm_factory),
                "sql": TextToSQLConversionAgent(llm_factory=self.llm_factory, db_schema_info=self.db_schema_info),
                "format": ResponseFormatterAgent(llm_factory=self.llm_factory),
                "validator": FileValidatorAgent(llm_factory=self.llm_factory),
                "extractor": DataExtractorAgent(llm_factory=self.llm_factory)
            }
            return True
        except Exception as e:
            logger.error(f"Failed to initialize agents: {str(e)}")
            return False
    
    async def test_agent(self, agent_name: str, query: str, file_path: Optional[str] = None):
        """
        Test a specific agent with a given query.
        
        Args:
            agent_name: Name of the agent to test
            query: User query to test
            file_path: Optional file path for file-based agents
        """
        if agent_name not in self.agents:
            logger.error(f"Unknown agent: {agent_name}")
            return
        
        agent = self.agents[agent_name]
        
        # Create agent input
        metadata = {}
        if file_path:
            # For file-based agents
            try:
                with open(file_path, "rb") as f:
                    content = f.read()
                metadata = {
                    "file_path": file_path,
                    "input_type": "image" if file_path.endswith((".jpg", ".png", ".jpeg")) else "document"
                }
            except Exception as e:
                logger.error(f"Failed to read file: {str(e)}")
                return
        else:
            # For text-based agents
            content = query
        
        agent_input = AgentInput(content=content, metadata=metadata)
        context = AgentContext(conversation_history=self.conversation_history)
        
        # Process the input
        try:
            logger.info(f"Processing input with {agent_name} agent...")
            result = await agent.process(agent_input, context)
            
            # Update conversation history
            self.conversation_history.append({"role": "user", "content": query})
            if hasattr(result, "content"):
                if isinstance(result.content, dict):
                    self.conversation_history.append({"role": "assistant", "content": json.dumps(result.content)})
                else:
                    self.conversation_history.append({"role": "assistant", "content": str(result.content)})
            
            # Print the result
            print("\n" + "="*50)
            print(f"AGENT: {agent_name}")
            print(f"STATUS: {result.status}")
            print(f"CONFIDENCE: {result.confidence}")
            print("-"*50)
            print("CONTENT:")
            if isinstance(result.content, dict):
                print(json.dumps(result.content, indent=2))
            else:
                print(result.content)
            print("-"*50)
            
            if hasattr(result, "metadata") and result.metadata:
                print("METADATA:")
                print(json.dumps(result.metadata, indent=2))
            
            if hasattr(result, "error") and result.error:
                print("ERROR:")
                print(result.error)
            
            print("="*50 + "\n")
            
        except Exception as e:
            logger.error(f"Error testing agent: {str(e)}")
    
    def start_console(self):
        """Start the interactive testing console."""
        if not self.init_agents():
            logger.error("Failed to initialize agents. Interactive mode not available.")
            return
            
        print("\n" + "="*50)
        print("WhatsApp Invoice Assistant - Interactive Testing Console")
        print("="*50)
        print("Type 'help' for available commands, 'exit' to quit.")
        print("="*50 + "\n")
        
        while True:
            try:
                cmd = input("> ").strip()
                
                if cmd == "exit":
                    break
                    
                elif cmd == "help":
                    print("\nAvailable commands:")
                    print("  test <agent> <query>  - Test an agent with a query")
                    print("  file <agent> <path>   - Test a file-based agent with a file")
                    print("  history               - Show conversation history")
                    print("  clear                 - Clear conversation history")
                    print("  agents                - List available agents")
                    print("  exit                  - Exit the console")
                    print("")
                    
                elif cmd == "agents":
                    print("\nAvailable agents:")
                    for name in self.agents:
                        print(f"  {name} - {self.agents[name].__class__.__name__}")
                    print("")
                    
                elif cmd == "history":
                    print("\nConversation history:")
                    for i, message in enumerate(self.conversation_history):
                        role = message.get("role", "unknown")
                        content = message.get("content", "")
                        print(f"[{i}] {role}: {content[:100]}{'...' if len(content) > 100 else ''}")
                    print("")
                    
                elif cmd == "clear":
                    self.conversation_history = []
                    print("Conversation history cleared.")
                    
                elif cmd.startswith("test "):
                    parts = cmd.split(" ", 2)
                    if len(parts) < 3:
                        print("Usage: test <agent> <query>")
                        continue
                        
                    agent_name = parts[1]
                    query = parts[2]
                    
                    if agent_name not in self.agents:
                        print(f"Unknown agent: {agent_name}")
                        print(f"Available agents: {', '.join(self.agents.keys())}")
                        continue
                        
                    self.loop.run_until_complete(self.test_agent(agent_name, query))
                    
                elif cmd.startswith("file "):
                    parts = cmd.split(" ", 2)
                    if len(parts) < 3:
                        print("Usage: file <agent> <path>")
                        continue
                        
                    agent_name = parts[1]
                    file_path = parts[2]
                    
                    if agent_name not in self.agents:
                        print(f"Unknown agent: {agent_name}")
                        print(f"Available agents: {', '.join(self.agents.keys())}")
                        continue
                        
                    if not os.path.exists(file_path):
                        print(f"File not found: {file_path}")
                        continue
                        
                    self.loop.run_until_complete(self.test_agent(agent_name, "", file_path))
                    
                else:
                    print("Unknown command. Type 'help' for available commands.")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error: {str(e)}")
        
        print("\nExiting interactive console...\n")


def main():
    """Main entry point for the test runner."""
    parser = argparse.ArgumentParser(description="WhatsApp Invoice Assistant Test Runner")
    
    # Add command-line arguments
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Run all tests")
    group.add_argument("--agent", type=str, help="Run tests for a specific agent")
    group.add_argument("--service", type=str, help="Run tests for a specific service")
    group.add_argument("--specific", type=str, help="Run a specific test (e.g., test_file.py::test_function)")
    group.add_argument("--status", action="store_true", help="Show test status")
    group.add_argument("--interactive", action="store_true", help="Start interactive testing console")
    
    args = parser.parse_args()
    
    # Execute the appropriate action based on arguments
    if args.all:
        return run_all_tests()
    elif args.agent:
        return run_agent_tests(args.agent)
    elif args.service:
        return run_service_tests(args.service)
    elif args.specific:
        return run_specific_test(args.specific)
    elif args.status:
        status = get_test_status()
        print("\nTest Status Summary:")
        print(f"Agent Test Files: {status['agent_test_files']}")
        print(f"Service Test Files: {status['service_test_files']}")
        print(f"Database Test Files: {status['database_test_files']}")
        print(f"Workflow Test Files: {status['workflow_test_files']}")
        print(f"Total Test Files: {status['total_test_files']}")
        print(f"Total Test Functions: {status['total_test_functions']}")
        print(f"Collection Status: {'Success' if status['collection_status'] else 'Failed'}")
        return 0
    elif args.interactive:
        console = AgentTestingConsole()
        console.start_console()
        return 0


if __name__ == "__main__":
    sys.exit(main()) 