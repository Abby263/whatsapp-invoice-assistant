#!/bin/bash

# Terminal colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print header
print_header() {
    echo -e "\n${BLUE}==========================================================${NC}"
    echo -e "${BLUE} WhatsApp Invoice Assistant - Docker Launcher              ${NC}"
    echo -e "${BLUE}==========================================================${NC}\n"
}

# Function to extract default values from config/env.yaml
extract_config_defaults() {
    echo -e "${YELLOW}Extracting default configuration values...${NC}"
    
    # Helper function to extract values using grep and sed
    extract_value() {
        local key="$1"
        local file="$2"
        local default="$3"
        
        # Try to extract the value from the config file
        local value=$(grep -A 1 "$key:" "$file" | tail -n 1 | sed -E 's/^[ ]+//g' | grep -v "^\$" || echo "")
        
        # If the value is empty or contains variable reference ${...}, use the default
        if [[ -z "$value" || "$value" == *"\${""*""}"* ]]; then
            echo "$default"
        else
            # Remove quotes if present
            echo "$value" | sed -E 's/^"(.*)"$/\1/' | sed -E "s/^'(.*)'$/\1/"
        fi
    }
    
    # Define the config file path
    CONFIG_FILE="config/env.yaml"
    
    # Check if config file exists
    if [ ! -f "$CONFIG_FILE" ]; then
        echo -e "${YELLOW}Config file not found. Using default values.${NC}"
        return
    fi
    
    # Extract database values
    DB_URL="postgresql://postgres:postgres@whatsapp-invoice-assistant-db:5432/whatsapp_invoice_assistant"
    MONGODB_URL="mongodb://whatsapp-invoice-assistant-mongodb:27017/whatsapp_invoice_assistant"
    
    # Extract Redis URL
    REDIS_URL=$(extract_value "url:" "$CONFIG_FILE" "redis://localhost:6379/0")
    
    # Extract logging level
    LOG_LEVEL=$(extract_value "level:" "$CONFIG_FILE" "INFO")
    
    echo -e "${GREEN}Extracted configuration values successfully.${NC}"
}

# Create or ensure the .env file exists
ensure_env_file() {
    # First extract defaults from config
    extract_config_defaults
    
    if [ ! -f .env ]; then
        echo -e "${YELLOW}No .env file found. Creating a default one...${NC}"
        cat > .env << EOL
# Database Configuration
DATABASE_URL=${DB_URL:-postgresql://postgres:postgres@whatsapp-invoice-assistant-db:5432/whatsapp_invoice_assistant}
USE_MONGODB=true
MONGODB_URI=${MONGODB_URL:-mongodb://whatsapp-invoice-assistant-mongodb:27017/whatsapp_invoice_assistant}

# OpenAI Configuration
OPENAI_API_KEY=your-api-key

# Twilio Configuration
TWILIO_ACCOUNT_SID=your-twilio-account-sid
TWILIO_AUTH_TOKEN=your-twilio-auth-token
TWILIO_PHONE_NUMBER=your-twilio-phone-number

# AWS Configuration
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
S3_BUCKET_NAME=your-s3-bucket-name
S3_REGION=us-east-1

# Redis Configuration
REDIS_URL=${REDIS_URL:-redis://localhost:6379/0}

# Logging Configuration
LOG_LEVEL=${LOG_LEVEL:-INFO}
EOL
        echo -e "${YELLOW}Please edit the .env file with your actual API keys and credentials.${NC}"
        echo -e "${YELLOW}Then run this script again.${NC}"
        exit 1
    fi

    # Check for critical variables
    if grep -q "OPENAI_API_KEY=your-api-key" .env; then
        echo -e "${YELLOW}Warning: OPENAI_API_KEY is not set in .env file.${NC}"
        echo -e "${YELLOW}The application will not function correctly without this key.${NC}"
        
        read -p "Would you like to enter your OpenAI API key now? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            read -p "Enter your OpenAI API key: " apikey
            sed -i.bak "s/OPENAI_API_KEY=your-api-key/OPENAI_API_KEY=${apikey}/" .env
            rm -f .env.bak 2>/dev/null
            echo -e "${GREEN}OpenAI API key updated in .env file.${NC}"
        else
            echo -e "${YELLOW}Continuing without setting OPENAI_API_KEY...${NC}"
        fi
    fi
}

# Create required directories
create_directories() {
    mkdir -p uploads
    mkdir -p logs
    echo -e "${GREEN}Created required directories.${NC}"
}

# Check Docker and Docker Compose
check_docker() {
    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Docker is not installed. Please install Docker first.${NC}"
        exit 1
    fi

    # On macOS, check if Docker Desktop is running
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # Check if Docker Desktop process is running
        if ! pgrep -f "Docker Desktop" > /dev/null; then
            echo -e "${RED}Docker Desktop is not running on your Mac.${NC}"
            echo -e "${YELLOW}Please start Docker Desktop from Applications.${NC}"
            
            read -p "Would you like to try opening Docker Desktop now? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo -e "${YELLOW}Attempting to open Docker Desktop...${NC}"
                open -a "Docker Desktop"
                echo -e "${YELLOW}Waiting for Docker Desktop to start (up to 30 seconds)...${NC}"
                
                for i in {1..30}; do
                    echo -n "."
                    sleep 1
                    if docker ps &>/dev/null; then
                        echo -e "\n${GREEN}Docker Desktop is now running!${NC}"
                        break
                    fi
                    
                    if [ $i -eq 30 ]; then
                        echo -e "\n${YELLOW}Docker Desktop might need more time to start.${NC}"
                        echo -e "${YELLOW}Please run this script again after Docker Desktop is fully started.${NC}"
                        exit 1
                    fi
                done
            else
                exit 1
            fi
        fi
    fi

    # Test Docker connection
    echo -e "${YELLOW}Testing Docker connection...${NC}"
    if ! docker ps &>/dev/null; then
        echo -e "${RED}Cannot connect to Docker daemon.${NC}"
        echo -e "${YELLOW}Please ensure Docker is running and try again.${NC}"
        exit 1
    fi
    echo -e "${GREEN}Docker is running properly.${NC}"

    # Check Docker Compose
    if command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE="docker-compose"
    elif docker compose version &>/dev/null; then
        DOCKER_COMPOSE="docker compose"
    else
        echo -e "${RED}Docker Compose not found. Please install Docker Compose.${NC}"
        exit 1
    fi
    echo -e "${GREEN}Using ${DOCKER_COMPOSE} for container orchestration.${NC}"
}

# Check for port conflicts
check_port_conflicts() {
    PORT_CONFLICT=false

    # Check PostgreSQL port
    echo -e "${YELLOW}Checking for port conflicts...${NC}"
    if nc -z localhost 5433 &>/dev/null; then
        echo -e "${YELLOW}Port 5433 (PostgreSQL) is already in use.${NC}"
        PORT_CONFLICT=true
    fi

    # Check MongoDB port
    if nc -z localhost 27018 &>/dev/null; then
        echo -e "${YELLOW}Port 27018 (MongoDB) is already in use.${NC}"
        PORT_CONFLICT=true
    fi

    # Check UI port
    if nc -z localhost 5001 &>/dev/null; then
        echo -e "${YELLOW}Port 5001 (UI) is already in use.${NC}"
        PORT_CONFLICT=true
    fi

    if [ "$PORT_CONFLICT" = true ]; then
        echo -e "${YELLOW}Some required ports are in use. This may cause conflicts.${NC}"
        read -p "Would you like to stop existing Docker containers? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${YELLOW}Stopping existing Docker containers...${NC}"
            $DOCKER_COMPOSE down
            echo -e "${GREEN}Containers stopped.${NC}"
        else
            echo -e "${YELLOW}Continuing with port conflicts. This may cause issues.${NC}"
        fi
    else
        echo -e "${GREEN}No port conflicts detected.${NC}"
    fi
}

# Start containers
start_containers() {
    echo -e "${YELLOW}Building and starting containers...${NC}"
    
    # Export environment variables from .env
    if [ -f .env ]; then
        export $(grep -v '^#' .env | xargs)
    fi
    
    # Build and start containers
    if ! $DOCKER_COMPOSE up -d --build; then
        echo -e "${RED}Failed to build and start containers.${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}Containers started successfully.${NC}"
    
    # Wait for services to be healthy
    echo -e "${YELLOW}Waiting for services to be ready...${NC}"
    for i in {1..30}; do
        if docker ps | grep -q "whatsapp-invoice-assistant-ui" && \
           docker ps | grep -q "whatsapp-invoice-assistant-db (healthy)" && \
           docker ps | grep -q "whatsapp-invoice-assistant-mongodb (healthy)"; then
            echo -e "${GREEN}All services are ready!${NC}"
            break
        fi
        
        echo -n "."
        sleep 2
        
        if [ $i -eq 30 ]; then
            echo -e "\n${YELLOW}Timeout waiting for services to be ready.${NC}"
            echo -e "${YELLOW}Please check container logs with 'docker logs whatsapp-invoice-assistant-ui'${NC}"
        fi
    done
}

# Display connection information
show_connection_info() {
    echo -e "\n${GREEN}==== Connection Information ====${NC}"
    echo -e "${GREEN}Web UI:${NC} http://localhost:5001"
    echo -e "${GREEN}MongoDB:${NC} mongodb://localhost:27018/whatsapp_invoice_assistant"
    echo -e "${GREEN}PostgreSQL:${NC} postgresql://postgres:postgres@localhost:5433/whatsapp_invoice_assistant"
    
    echo -e "\n${YELLOW}To stop the containers, run:${NC}"
    echo -e "  ${BLUE}make docker-stop${NC}   or   ${BLUE}docker-compose down${NC}"
    
    echo -e "\n${YELLOW}To view logs:${NC}"
    echo -e "  ${BLUE}docker logs whatsapp-invoice-assistant-ui${NC}"
}

# Main execution
print_header
ensure_env_file
create_directories
check_docker
check_port_conflicts
start_containers
show_connection_info 