// DOM Elements
const chatMessages = document.getElementById('chatMessages');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const attachBtn = document.getElementById('attachBtn');
const fileInput = document.getElementById('fileInput');
const uploadForm = document.getElementById('uploadForm');
const newConversationBtn = document.getElementById('newConversationBtn');
const helpBtn = document.getElementById('helpBtn');
const loadingOverlay = document.getElementById('loadingOverlay');
const togglePanelBtn = document.getElementById('togglePanelBtn');
const agentPanel = document.querySelector('.agent-panel');
const currentIntent = document.getElementById('currentIntent');
const workflowSteps = document.getElementById('workflowSteps');
const invoiceCount = document.getElementById('invoiceCount');
const itemCount = document.getElementById('itemCount');
const userIdDisplay = document.getElementById('userIdDisplay');
const whatsappNumberSelect = document.getElementById('whatsappNumberSelect');
const s3StorageSection = document.getElementById('s3StorageSection');
const s3FileKey = document.getElementById('s3FileKey');
const s3Url = document.getElementById('s3Url');
const s3UrlContainer = document.getElementById('s3UrlContainer');
const dbUserItemsCount = document.getElementById('db-user-items-count');
const dbUserInvoicesCount = document.getElementById('db-user-invoices-count');
const dashboardReceiptCount = document.getElementById('dashboardReceiptCount');
const dashboardItemCount = document.getElementById('dashboardItemCount');
const dashboardIntent = document.getElementById('dashboardIntent');
const dashboardDbStatus = document.getElementById('dashboardDbStatus');
const dashboardStorageStatus = document.getElementById('dashboardStorageStatus');
const dashboardVectorStatus = document.getElementById('dashboardVectorStatus');
const storageProvider = document.getElementById('storageProvider');
const themeToggleBtn = document.getElementById('themeToggleBtn');
const themeToggleIcon = document.getElementById('themeToggleIcon');
const themeToggleLabel = document.getElementById('themeToggleLabel');

// Global variables
let isProcessing = false;
let conversationId = generateUUID();
let userId = "0";
let whatsappNumber = "+1234567890"; // Default WhatsApp number

function setElementText(element, value) {
    if (element) {
        element.textContent = value;
    }
}

function setDashboardStatus(element, value, active = true) {
    if (!element) {
        return;
    }

    element.textContent = value;
    element.classList.toggle('status-active', active);
    element.classList.toggle('status-inactive', !active);
}

function updateFileStorageInfo(storage) {
    if (!storage || Object.keys(storage).length === 0) {
        return;
    }

    s3StorageSection.style.display = 'block';
    const provider = storage.provider || 'Supabase';
    setElementText(storageProvider, provider);
    s3FileKey.textContent = storage.file_key || storage.path || 'None';
    setDashboardStatus(dashboardStorageStatus, provider, true);

    if (storage.url) {
        s3Url.href = storage.url;
        s3Url.textContent = 'View File';
        s3UrlContainer.style.display = 'block';
    } else {
        s3Url.href = '#';
        s3Url.textContent = 'None';
    }
}

// Initialize application
document.addEventListener('DOMContentLoaded', () => {
    setupTheme();
    initializeApp();
    updateDatabaseCounts();
    loadUsers();

    // Set user information in the UI
    userIdDisplay.textContent = userId;

    // Setup WhatsApp number select event handling
    whatsappNumberSelect.addEventListener('change', switchUser);

    // Setup create user button
    const createUserBtn = document.getElementById('createUserBtn');
    if (createUserBtn) {
        createUserBtn.addEventListener('click', showCreateUserDialog);
    }

    // Setup company profile button
    const companyProfileBtn = document.getElementById('companyProfileBtn');
    if (companyProfileBtn) {
        companyProfileBtn.addEventListener('click', showCompanyProfileModal);
    }

    // Initialize memory configuration
    setupMemoryConfigControls();
    updateMemoryConfig();

    // Initialize vector embeddings controls
    setupVectorEmbeddingsControls();
    setupCommandCenter();

    // Initialize UI when document is ready
    initUI();

    // Set up event listeners
    setupEventListeners();
});

function setupTheme() {
    const savedTheme = localStorage.getItem('invoice-ui-theme');
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    const initialTheme = savedTheme || (prefersDark ? 'dark' : 'light');

    applyTheme(initialTheme);

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', () => {
            const currentTheme = document.documentElement.dataset.theme || 'light';
            const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
            applyTheme(nextTheme);
            localStorage.setItem('invoice-ui-theme', nextTheme);
        });
    }
}

function applyTheme(theme) {
    const normalizedTheme = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.theme = normalizedTheme;

    if (themeToggleIcon) {
        themeToggleIcon.className = normalizedTheme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
    }

    setElementText(themeToggleLabel, normalizedTheme === 'dark' ? 'Light' : 'Dark');

    if (themeToggleBtn) {
        themeToggleBtn.setAttribute(
            'aria-label',
            normalizedTheme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'
        );
    }
}

function setupCommandCenter() {
    document.querySelectorAll('[data-prompt]').forEach(button => {
        if (button.dataset.bound === 'true') {
            return;
        }

        button.dataset.bound = 'true';
        button.addEventListener('click', () => {
            if (isProcessing) {
                return;
            }

            const prompt = button.dataset.prompt;
            messageInput.value = prompt;
            messageInput.focus();
            sendMessage();
        });
    });

    document.querySelectorAll('[data-upload-trigger]').forEach(button => {
        if (button.dataset.bound === 'true') {
            return;
        }

        button.dataset.bound = 'true';
        button.addEventListener('click', () => {
            if (!isProcessing) {
                fileInput.click();
            }
        });
    });
}

// Function to load users into the dropdown
function loadUsers() {
    fetch('/api/users')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success' && Array.isArray(data.users)) {
                // Save current value
                const currentValue = whatsappNumberSelect.value;

                // Clear existing options
                whatsappNumberSelect.innerHTML = '';

                // Add users to dropdown
                data.users.forEach(user => {
                    const option = document.createElement('option');
                    option.value = user.whatsapp_number;
                    option.textContent = `${user.name} (${user.whatsapp_number})`;
                    option.dataset.userId = user.id;
                    whatsappNumberSelect.appendChild(option);
                });

                // Try to restore previous selection, or select first user
                if (data.users.length > 0) {
                    // Try to find and select the option with the current WhatsApp number
                    const matchingOption = Array.from(whatsappNumberSelect.options).find(
                        option => option.value === currentValue
                    );

                    if (matchingOption) {
                        whatsappNumberSelect.value = currentValue;
                    } else {
                        // Default to first user
                        whatsappNumberSelect.selectedIndex = 0;
                        whatsappNumber = whatsappNumberSelect.value;

                        // Get the user ID from the selected option
                        const selectedOption = whatsappNumberSelect.options[whatsappNumberSelect.selectedIndex];
                        if (selectedOption.dataset.userId) {
                            userId = selectedOption.dataset.userId;
                            userIdDisplay.textContent = userId;
                        }
                    }

                    updateSelectedUser();
                    updateDatabaseCounts();
                } else {
                    const option = document.createElement('option');
                    option.value = whatsappNumber;
                    option.textContent = whatsappNumber;
                    option.dataset.userId = userId;
                    whatsappNumberSelect.appendChild(option);
                    whatsappNumberSelect.value = whatsappNumber;
                    updateSelectedUser();
                }
            } else {
                console.error('Failed to load users:', data.message);
            }
        })
        .catch(error => {
            console.error('Error loading users:', error);
        });
}

// Function to switch the active user
function switchUser() {
    if (isProcessing) {
        // Don't allow switching while processing a request
        return;
    }

    const newWhatsappNumber = whatsappNumberSelect.value;

    // Get the user ID from the selected option
    const selectedOption = whatsappNumberSelect.options[whatsappNumberSelect.selectedIndex];
    const newUserId = selectedOption.dataset.userId;

    // If user hasn't changed, do nothing
    if (newWhatsappNumber === whatsappNumber && newUserId === userId) {
        return;
    }

    // Update global variables
    whatsappNumber = newWhatsappNumber;

    if (newUserId) {
        userId = newUserId;
        userIdDisplay.textContent = userId;
    }

    // Initialize a new conversation for this user
    initializeForUser(whatsappNumber);
}

// Function to initialize for a specific user
function initializeForUser(whatsappNumber) {
    showLoading();

    fetch(`/api/init?whatsapp_number=${encodeURIComponent(whatsappNumber)}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // Update user information
                if (data.user_id) {
                    userId = data.user_id;
                    userIdDisplay.textContent = userId;
                }

                // Reset the chat
                addSystemMessage(`Switched to user with WhatsApp number: ${whatsappNumber}`);

                // Clear workflow steps
                workflowSteps.innerHTML = '<div class="step waiting"><span class="step-dot"></span><span>Waiting for input...</span></div>';

                // Reset intent
                currentIntent.textContent = 'None';
                setElementText(dashboardIntent, 'None');

                // Reset token counts
                document.getElementById('inputTokens').textContent = '0';
                document.getElementById('outputTokens').textContent = '0';
                document.getElementById('totalTokens').textContent = '0';

                // Update database counts for this user
                updateDatabaseCounts();
            } else {
                addSystemMessage(`Error initializing for user: ${data.message}`);
            }

            hideLoading();
        })
        .catch(error => {
            console.error('Error initializing for user:', error);
            addSystemMessage(`Error initializing for user: ${error.message}`);
            hideLoading();
        });
}

// Event Listeners
sendBtn.addEventListener('click', sendMessage);
messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

attachBtn.addEventListener('click', () => {
    fileInput.click();
});

fileInput.addEventListener('change', uploadFile);

togglePanelBtn.addEventListener('click', () => {
    agentPanel.classList.toggle('panel-collapsed');
});

newConversationBtn.addEventListener('click', startNewConversation);

helpBtn.addEventListener('click', () => {
    sendCommand('/help');
});

// Functions
function initializeApp() {
    fetch('/api/init')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                console.log('Test environment initialized');

                // Update user information
                if (data.user_id) {
                    userId = data.user_id;
                    userIdDisplay.textContent = userId;
                }

                if (data.whatsapp_number) {
                    whatsappNumber = data.whatsapp_number;

                    // Will be set by loadUsers, but set as fallback
                    if (whatsappNumberSelect.options.length === 0) {
                        const option = document.createElement('option');
                        option.value = whatsappNumber;
                        option.textContent = whatsappNumber;
                        whatsappNumberSelect.appendChild(option);
                        whatsappNumberSelect.value = whatsappNumber;
                    }
                }

            } else {
                console.error('Failed to initialize test environment:', data.message);
                addSystemMessage('Failed to initialize test environment. Please check the server logs.');
            }
        })
        .catch(error => {
            console.error('Error initializing test environment:', error);
            addSystemMessage('Error initializing test environment. Please check the server logs.');
        });
}

function sendMessage() {
    const message = messageInput.value.trim();
    if (message && !isProcessing) {
        // Clear input
        messageInput.value = '';

        // Add user message to chat
        addMessage(message, 'outgoing');

        // Process the message
        processMessage(message);
    }
}

function processMessage(message) {
    // Set processing state
    isProcessing = true;
    showLoading();

    // Update agent panel
    currentIntent.textContent = 'Analyzing...';
    setElementText(dashboardIntent, 'Analyzing');
    addWorkflowStep('InputRouter', 'active');

    // Send message to server
    fetch('/api/message', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            message: message,
            conversation_id: conversationId,
            user_id: userId,
            whatsapp_number: whatsappNumber
        })
    })
    .then(response => response.json())
    .then(data => {
        // Add response message to chat
        if (data.status === 'success') {
            // Check if there's a PDF file in the metadata
            let pdfFilename = null;
            if (data.metadata && (data.metadata.ui_pdf_filename || data.metadata.ui_pdf_url)) {
                // Extract PDF filename from either the filename or URL field
                pdfFilename = data.metadata.ui_pdf_filename ||
                              (data.metadata.ui_pdf_url ? data.metadata.ui_pdf_url.split('/').pop() : null);

                // Add a system message about the PDF
                if (pdfFilename) {
                    addSystemMessage(`Generated invoice PDF: ${pdfFilename}`);
                }
            }

            // Add the message with PDF attachment if available
            addMessage(data.message, 'incoming', pdfFilename);

            // Update agent panel with metadata
            updateAgentPanel(data);

            // Update database counts
                updateDatabaseCounts();

            // Update user information display if provided
            if (data.user_id) {
                userId = data.user_id;
                userIdDisplay.textContent = userId;
            }

            if (data.whatsapp_number) {
                whatsappNumber = data.whatsapp_number;
                // Update the select input value if it doesn't already match
                if (whatsappNumberSelect.value !== whatsappNumber) {
                    const matchingOption = Array.from(whatsappNumberSelect.options).find(
                        option => option.value === whatsappNumber
                    );

                    if (matchingOption) {
                        whatsappNumberSelect.value = whatsappNumber;
                    } else {
                        // If no matching option found, add one
                        const option = document.createElement('option');
                        option.value = whatsappNumber;
                        option.textContent = whatsappNumber;
                        whatsappNumberSelect.appendChild(option);
                        whatsappNumberSelect.value = whatsappNumber;
                    }
                }
            }
        } else {
            addSystemMessage(`Error: ${data.message}`);
        }

        // Reset processing state
        isProcessing = false;
        hideLoading();
    })
    .catch(error => {
        console.error('Error processing message:', error);
        addSystemMessage('An error occurred while processing your message.');

        // Reset processing state
        isProcessing = false;
        hideLoading();
    });
}

function sendCommand(command) {
    // Add command to chat
    addMessage(command, 'outgoing');

    // Process the command
    processMessage(command);
}

function uploadFile() {
    if (fileInput.files.length === 0 || isProcessing) {
        return;
    }

    // Set processing state
    isProcessing = true;
    showLoading();

    // Update agent panel
    currentIntent.textContent = 'Processing File...';
    setElementText(dashboardIntent, 'Processing file');
    addWorkflowStep('FileProcessor', 'active');

    // Create FormData
    const formData = new FormData(uploadForm);

    // Add WhatsApp number and user ID to the form data
    formData.append('whatsapp_number', whatsappNumber);
    formData.append('user_id', userId);

    // Send file to server
    fetch('/api/upload', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        // Add system message about upload
        addSystemMessage(`Uploaded file: ${fileInput.files[0].name}`);

        // Add response message to chat
        if (data.status === 'success') {
            addMessage(data.message, 'incoming', data.filename);

            // Update agent panel with metadata
            updateAgentPanel(data);

            // Update database counts
            updateDatabaseCounts();

            // Update user information display if provided
            if (data.user_id) {
                userId = data.user_id;
                userIdDisplay.textContent = userId;
            }

            if (data.whatsapp_number) {
                whatsappNumber = data.whatsapp_number;
                whatsappNumberSelect.value = whatsappNumber;
            }
        } else {
            addSystemMessage(`Error: ${data.message}`);
        }

        // Reset file input
        fileInput.value = '';

        // Reset processing state
        isProcessing = false;
        hideLoading();
    })
    .catch(error => {
        console.error('Error uploading file:', error);
        addSystemMessage('An error occurred while uploading your file.');

        // Reset file input
        fileInput.value = '';

        // Reset processing state
        isProcessing = false;
        hideLoading();
    });
}

function addMessage(content, type, filename = null) {
    const messageElement = document.createElement('div');
    messageElement.className = `message ${type}`;

    const messageContent = document.createElement('div');
    messageContent.className = 'message-content';

    // Format content with line breaks
    const formattedContent = content.replace(/\n/g, '<br>');
    messageContent.innerHTML = `<p>${formattedContent}</p>`;

    // Add file attachment if provided
    if (filename) {
        const fileExt = filename.split('.').pop().toLowerCase();
        let fileIcon = 'file';

        // Set icon based on file type
        if (['jpg', 'jpeg', 'png', 'gif'].includes(fileExt)) {
            fileIcon = 'file-image';

            // Add image preview
            const imgPreview = document.createElement('img');
            imgPreview.src = `/uploads/${filename}`;
            imgPreview.alt = filename;
            messageContent.appendChild(imgPreview);
        } else if (fileExt === 'pdf') {
            fileIcon = 'file-pdf';
        } else if (['doc', 'docx'].includes(fileExt)) {
            fileIcon = 'file-word';
        } else if (['xls', 'xlsx', 'csv'].includes(fileExt)) {
            fileIcon = 'file-excel';
        }

        // Add file attachment element
        const fileAttachment = document.createElement('div');
        fileAttachment.className = 'file-attachment';

        // Create the file icon and info elements
        const fileHTML = `
            <i class="fas fa-${fileIcon}"></i>
            <div class="file-info">
                <div class="file-name">${filename}</div>
                <div class="file-size">Processed</div>
            </div>
        `;

        // For PDFs, make them clickable with a link that opens in a new tab
        if (fileExt === 'pdf') {
            const fileLink = document.createElement('a');
            fileLink.href = `/uploads/${filename}`;
            fileLink.target = '_blank';
            fileLink.className = 'file-link';
            fileLink.innerHTML = fileHTML;
            fileLink.title = "Click to open PDF";
            fileAttachment.appendChild(fileLink);

            // Add a view button
            const viewButton = document.createElement('button');
            viewButton.className = 'view-file-btn';
            viewButton.innerHTML = '<i class="fas fa-external-link-alt"></i>';
            viewButton.title = "Open in new tab";
            viewButton.onclick = function() {
                window.open(`/uploads/${filename}`, '_blank');
            };
            fileAttachment.appendChild(viewButton);
        } else {
            fileAttachment.innerHTML = fileHTML;
        }

        messageContent.appendChild(fileAttachment);
    }

    const messageTime = document.createElement('div');
    messageTime.className = 'message-time';
    messageTime.textContent = getCurrentTime();

    messageElement.appendChild(messageContent);
    messageElement.appendChild(messageTime);

    chatMessages.appendChild(messageElement);

    // Scroll to bottom
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addSystemMessage(message) {
    const messageElement = document.createElement('div');
    messageElement.className = 'message system';

    const messageContent = document.createElement('div');
    messageContent.className = 'message-content';
    messageContent.innerHTML = `<p>${message}</p>`;

    const messageTime = document.createElement('div');
    messageTime.className = 'message-time';
    messageTime.textContent = getCurrentTime();

    messageElement.appendChild(messageContent);
    messageElement.appendChild(messageTime);

    chatMessages.appendChild(messageElement);

    // Scroll to bottom
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function getCurrentTime() {
    const now = new Date();
    const hours = now.getHours().toString().padStart(2, '0');
    const minutes = now.getMinutes().toString().padStart(2, '0');
    return `${hours}:${minutes}`;
}

function showLoading(message = "Loading...") {
    loadingOverlay.classList.remove('hidden');
    const loadingText = document.querySelector('#loadingOverlay .loading-text');
    if (loadingText) {
        loadingText.textContent = message;
    }
}

function hideLoading() {
    loadingOverlay.classList.add('hidden');
}

function startNewConversation() {
    // Call the init endpoint to reset conversation ID on the server
    fetch('/api/init')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
    // Add system message
    addSystemMessage('Starting a new conversation.');

    // Clear workflow steps
                workflowSteps.innerHTML = '<div class="step waiting"><span class="step-dot"></span><span>Waiting for input...</span></div>';

    // Reset intent
    currentIntent.textContent = 'None';
    setElementText(dashboardIntent, 'None');

                // Reset token counts
                document.getElementById('inputTokens').textContent = '0';
                document.getElementById('outputTokens').textContent = '0';
                document.getElementById('totalTokens').textContent = '0';
            } else {
                addSystemMessage('Error starting new conversation: ' + data.message);
            }
        })
        .catch(error => {
            console.error('Error starting new conversation:', error);
            addSystemMessage('Error starting new conversation. Please try again.');
        });
}

function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

function updateAgentPanel(data) {
    // Update intent from message data
    if (data.metadata && data.metadata.intent) {
        currentIntent.textContent = data.metadata.intent;
        setElementText(dashboardIntent, data.metadata.intent);
    }

    // Update token usage if available
    const inputTokens = document.getElementById('inputTokens');
    const outputTokens = document.getElementById('outputTokens');
    const totalTokens = document.getElementById('totalTokens');

    if (data.metadata && data.metadata.token_usage) {
        const tokenUsage = data.metadata.token_usage;

        if (inputTokens && tokenUsage.input_tokens !== undefined) {
            inputTokens.textContent = tokenUsage.input_tokens.toLocaleString();
        }

        if (outputTokens && tokenUsage.output_tokens !== undefined) {
            outputTokens.textContent = tokenUsage.output_tokens.toLocaleString();
        }

        if (totalTokens && tokenUsage.total_tokens !== undefined) {
            totalTokens.textContent = tokenUsage.total_tokens.toLocaleString();
        } else if (totalTokens && tokenUsage.input_tokens !== undefined && tokenUsage.output_tokens !== undefined) {
            // Calculate total if not provided
            totalTokens.textContent = (tokenUsage.input_tokens + tokenUsage.output_tokens).toLocaleString();
        }
    }

    // If this is a file upload, check for stored file info first
    if (data.type === 'file') {
        fetch('/api/file-storage-info')
            .then(response => response.json())
            .then(storageData => {
                const storage = storageData.file_storage || storageData.s3_storage;
                if (storageData.status === 'success' && storage) {
                    updateFileStorageInfo(storage);
                    console.log("Successfully retrieved file storage info:", storage);
                }
            })
            .catch(error => {
                console.error('Error fetching file storage info:', error);
            });
    }

    // Fetch the latest agent flow data which includes real workflow steps from logs
    fetch('/api/agent-flow')
        .then(response => response.json())
        .then(flowData => {
            if (flowData.status === 'success') {
                // Update intent if available in flow data
                if (flowData.intent && flowData.intent !== 'unknown') {
                    currentIntent.textContent = flowData.intent;
                    setElementText(dashboardIntent, flowData.intent);
                }

                // Clear existing workflow steps
                workflowSteps.innerHTML = '';

                // Add each workflow step with completed status
                if (flowData.nodes && flowData.nodes.length > 0) {
                    flowData.nodes.forEach(step => {
                        addWorkflowStep(step, 'completed');
                    });
                } else {
                    // If no steps available, show waiting step
                    workflowSteps.innerHTML = '<div class="step waiting"><span class="step-dot"></span><span>Waiting for input...</span></div>';
                }

                // Update user information if available
                if (flowData.user_id) {
                    userId = flowData.user_id;
                    userIdDisplay.textContent = userId;
                }

                if (flowData.whatsapp_number) {
                    whatsappNumber = flowData.whatsapp_number;
                    whatsappNumberSelect.value = whatsappNumber;
                }

                const flowStorage = flowData.file_storage || flowData.s3_storage;
                if (flowStorage && Object.keys(flowStorage).length > 0 && s3StorageSection.style.display !== 'block') {
                    updateFileStorageInfo(flowStorage);
                }
            } else {
                console.error('Error fetching agent flow data:', flowData.message);
            }
        })
        .catch(error => {
            console.error('Error fetching agent flow data:', error);
        });

    // Update database counts after each message
    updateDatabaseCounts();
}

function addWorkflowStep(stepName, status) {
    // Check if step already exists
    const existingStep = Array.from(workflowSteps.children).find(step =>
        step.textContent.includes(stepName)
    );

    if (existingStep) {
        // Update existing step
        existingStep.className = `step ${status}`;
    } else {
        // Create new step
        const stepElement = document.createElement('div');
        stepElement.className = `step ${status}`;

        // Create dot indicator
        const dotElement = document.createElement('span');
        dotElement.className = 'step-dot';
        stepElement.appendChild(dotElement);

        // Create step text
        const textElement = document.createElement('span');
        textElement.textContent = stepName;
        stepElement.appendChild(textElement);

        // Add click handler to show logs
        stepElement.addEventListener('click', function() {
            showStepLogs(stepName);
        });

        // Remove waiting step if this is the first step
        if (workflowSteps.children.length === 1 &&
            workflowSteps.children[0].classList.contains('waiting')) {
            workflowSteps.innerHTML = '';
        }

        workflowSteps.appendChild(stepElement);
    }
}

function showStepLogs(stepName) {
    // Show loading
    showLoading();

    // Fetch logs for the step
    fetch(`/api/step-logs/${stepName}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                const stepStorage = data.file_storage || data.s3_storage;
                if (stepStorage && Object.keys(stepStorage).length > 0) {
                    updateFileStorageInfo(stepStorage);
                    console.log("Updated file storage info from step logs:", stepStorage);
                }

                // Create logs modal
                const modalOverlay = document.createElement('div');
                modalOverlay.className = 'modal-overlay';

                const modalContent = document.createElement('div');
                modalContent.className = 'modal-content';

                const modalHeader = document.createElement('div');
                modalHeader.className = 'modal-header';
                modalHeader.innerHTML = `
                    <h3>${stepName} Logs</h3>
                    <button class="close-modal">&times;</button>
                `;

                const modalBody = document.createElement('div');
                modalBody.className = 'modal-body';

                // Add file storage info if available
                if (stepStorage && Object.keys(stepStorage).length > 0) {
                    const s3InfoSection = document.createElement('div');
                    s3InfoSection.className = 'storage-info-section';
                    s3InfoSection.innerHTML = `
                        <h4>File Storage Information</h4>
                        <div class="s3-storage-info">
                            ${stepStorage.file_key ? `<div class="storage-item">
                                <span class="label">File Key:</span>
                                <span class="value">${stepStorage.file_key}</span>
                            </div>` : ''}
                            ${stepStorage.url ? `<div class="storage-item">
                                <span class="label">URL:</span>
                                <div class="value">
                                    <a href="${stepStorage.url}" target="_blank">View File</a>
                                </div>
                            </div>` : ''}
                            ${stepStorage.bucket ? `<div class="storage-item">
                                <span class="label">Bucket:</span>
                                <span class="value">${stepStorage.bucket}</span>
                            </div>` : ''}
                        </div>
                    `;
                    modalBody.appendChild(s3InfoSection);
                }

                // Process and structure the logs
                if (data.logs && data.logs.length > 0) {
                    const logsContainer = document.createElement('div');
                    logsContainer.className = 'step-logs-container';

                    // Process logs to structure them better
                    const processedLogs = processStepLogs(data.logs, stepName);

                    // Add structured logs to container
                    processedLogs.forEach(logEntry => {
                        const logElement = document.createElement('div');
                        logElement.className = 'log-entry';

                        // Add timestamp
                        const timestamp = document.createElement('div');
                        timestamp.className = 'log-timestamp';
                        timestamp.textContent = logEntry.timestamp;
                        logElement.appendChild(timestamp);

                        // Add log content with level
                        const logContent = document.createElement('div');
                        logContent.className = 'log-content';

                        // Add log level badge
                        const levelBadge = document.createElement('span');
                        levelBadge.className = `log-level ${logEntry.level.toLowerCase()}`;
                        levelBadge.textContent = logEntry.level;
                        logContent.appendChild(levelBadge);

                        // Add log message
                        const message = document.createElement('span');
                        message.textContent = logEntry.message;
                        logContent.appendChild(message);

                        logElement.appendChild(logContent);

                        // If we have structured input/output data
                        if (logEntry.input || logEntry.output) {
                            const detailsContainer = document.createElement('div');
                            detailsContainer.className = 'log-step-details';

                            // Add userId if available
                            if (logEntry.userId) {
                                const userInfo = document.createElement('div');
                                userInfo.className = 'log-user-info';
                                userInfo.innerHTML = `<strong>User ID:</strong> ${logEntry.userId}`;
                                detailsContainer.appendChild(userInfo);
                            }

                            // Add input if available
                            if (logEntry.input) {
                                const inputElement = document.createElement('div');
                                inputElement.className = 'log-step-input';
                                inputElement.innerHTML = `<span class="log-step-label">Input:</span> ${logEntry.input}`;
                                detailsContainer.appendChild(inputElement);
                            }

                            // Add output if available
                            if (logEntry.output) {
                                const outputElement = document.createElement('div');
                                outputElement.className = 'log-step-output';
                                outputElement.innerHTML = `<span class="log-step-label">Output:</span> ${logEntry.output}`;
                                detailsContainer.appendChild(outputElement);
                            }

                            logElement.appendChild(detailsContainer);
                        }

                        logsContainer.appendChild(logElement);
                    });

                    modalBody.appendChild(logsContainer);
                } else {
                    const noLogsMessage = document.createElement('p');
                    noLogsMessage.textContent = 'No logs available for this step.';
                    modalBody.appendChild(noLogsMessage);
                }

                // Assemble modal
                modalContent.appendChild(modalHeader);
                modalContent.appendChild(modalBody);
                modalOverlay.appendChild(modalContent);

                // Add to body
                document.body.appendChild(modalOverlay);

                // Add close handlers
                const closeButton = modalOverlay.querySelector('.close-modal');
                closeButton.addEventListener('click', function() {
                    document.body.removeChild(modalOverlay);
                });

                modalOverlay.addEventListener('click', function(e) {
                    if (e.target === modalOverlay) {
                        document.body.removeChild(modalOverlay);
                    }
                });
            } else {
                console.error('Error fetching step logs:', data.message);
                addSystemMessage(`Error fetching logs for ${stepName}: ${data.message}`);
            }

            // Hide loading
            hideLoading();
        })
        .catch(error => {
            console.error('Error fetching step logs:', error);
            addSystemMessage(`Error fetching logs for ${stepName}`);
            hideLoading();
        });
}

function processStepLogs(logs, stepName) {
    // Process logs to extract structured information
    return logs.map(log => {
        // Extract timestamp and remaining content
        const parts = log.split(' - ');
        const timestamp = parts.shift().trim();
        const remaining = parts.join(' - ');

        // Extract level and message
        const levelMatch = remaining.match(/(\w+) - (.+)/);
        let level = 'INFO';
        let message = remaining;

        if (levelMatch) {
            level = levelMatch[1];
            message = levelMatch[2];
        }

        // Create base log entry
        const logEntry = {
            timestamp,
            level,
            message,
            input: null,
            output: null,
            userId: null
        };

        // Extract structured information based on the log message

        // Extract user ID if present
        const userIdMatch = message.match(/user_id[:|=]\s*(\d+)/i);
        if (userIdMatch) {
            logEntry.userId = userIdMatch[1];
        }

        // Extract input data if present
        const inputMatch = message.match(/with input:?\s*['"](.*?)['"]|input:?\s*['"](.*?)['"]|message:?\s*['"](.*?)['"]|query:?\s*['"](.*?)['"]/i);
        if (inputMatch) {
            // Find the first non-undefined match group (the actual input)
            const inputGroups = inputMatch.slice(1).filter(Boolean);
            if (inputGroups.length > 0) {
                logEntry.input = inputGroups[0];
            }
        } else if (message.includes('with input:') || message.includes('input:')) {
            // Check if it's a JSON input
            const jsonStartIndex = message.indexOf('{');
            if (jsonStartIndex > -1) {
                try {
                    // Try to extract and format the JSON part
                    const jsonPart = message.substring(jsonStartIndex);
                    const parsedJson = JSON.parse(jsonPart);
                    logEntry.input = JSON.stringify(parsedJson, null, 2);
                } catch (e) {
                    // If it's not valid JSON, just use the message after "with input:"
                    const inputPart = message.split(/with input:?|input:?/i)[1];
                    if (inputPart) {
                        logEntry.input = inputPart.trim();
                    }
                }
            }
        }

        // Extract output data if present
        if (message.includes('result:') || message.includes('response:') || message.includes('output:')) {
            const outputPart = message.split(/result:?|response:?|output:?/i)[1];
            if (outputPart) {
                logEntry.output = outputPart.trim();
            }
        }

        // For specific step types, try to extract more detailed information
        if (stepName === 'SQLGenerator' && message.includes('SQL query:')) {
            const sqlQuery = message.split('SQL query:')[1].trim();
            logEntry.output = `SQL: ${sqlQuery}`;
        } else if (stepName === 'DatabaseQuerier' && message.includes('results:')) {
            const resultsText = message.split('results:')[1].trim();
            logEntry.output = `Results: ${resultsText}`;
        }

        return logEntry;
    });
}

function updateDatabaseCounts() {
    fetch(`/api/db-status?user_id=${userId}`)
        .then(response => response.json())
        .then(data => {
            // Add connection status message to UI
            const pgConnection = document.getElementById('pg-connection');
            const mongoConnection = document.getElementById('mongo-connection');

            // Check for connection status information
            if (data.connection_status) {
                const status = data.connection_status;

                // Update PostgreSQL connection status
                if (pgConnection) {
                    if (status.success) {
                        pgConnection.textContent = "Connected";
                        pgConnection.classList.add('status-active');
                        pgConnection.classList.remove('status-inactive');
                        setDashboardStatus(dashboardDbStatus, 'Connected', true);
                    } else {
                        pgConnection.textContent = "Not Connected";
                        pgConnection.classList.add('status-inactive');
                        pgConnection.classList.remove('status-active');
                        setDashboardStatus(dashboardDbStatus, 'Offline', false);

                        // Show error message if available
                        if (status.message && status.message.includes('Database connection error')) {
                            console.warn('PostgreSQL connection unavailable:', status.message);
                            // Add error tooltip or notification if needed
                            pgConnection.title = status.message;
                        }
                    }
                }
            }

            if (data.status === 'success') {
                // Update invoice and item counts
                const dbInvoicesCount = document.getElementById('db-invoices-count');
                const dbUserInvoicesCount = document.getElementById('db-user-invoices-count');
                const dbItemsCount = document.getElementById('db-items-count');
                const dbUserItemsCount = document.getElementById('db-user-items-count');
                const dbSize = document.getElementById('db-size');
                const tablesSize = document.getElementById('tables-size');

                if (dbInvoicesCount) {
                    dbInvoicesCount.textContent = data.counts.invoices.total || 0;
                }

                if (dbUserInvoicesCount) {
                    dbUserInvoicesCount.textContent = data.counts.invoices.user_specific || 0;
                }

                setElementText(dashboardReceiptCount, data.counts.invoices.user_specific || 0);

                if (dbItemsCount) {
                    dbItemsCount.textContent = data.counts.items || 0;
                }

                if (dbUserItemsCount) {
                    dbUserItemsCount.textContent = data.counts.user_items || 0;
                }

                setElementText(dashboardItemCount, data.counts.user_items || 0);

                // Fallback for old UI elements
                if (invoiceCount) {
                    invoiceCount.textContent = data.counts.invoices.total || 0;
                }

                if (itemCount) {
                    itemCount.textContent = data.counts.items || 0;
                }

                // Update database size info if available
                if (data.size_info) {
                    if (data.size_info.total_size) {
                        if (dbSize) dbSize.textContent = data.size_info.total_size;
                        if (document.getElementById('dbSize')) document.getElementById('dbSize').textContent = data.size_info.total_size;
                    }

                    if (data.size_info.tables_size) {
                        if (tablesSize) tablesSize.textContent = data.size_info.tables_size;
                        if (document.getElementById('tablesSize')) document.getElementById('tablesSize').textContent = data.size_info.tables_size;
                    }
                }

                // Update connection info
                if (data.connection_info) {
                    // Format MongoDB connection info
                    if (mongoConnection && data.connection_info.mongodb) {
                        const mongo = data.connection_info.mongodb;
                        mongoConnection.textContent = `${mongo.host}:${mongo.port}/${mongo.database}`;
                    }
                }

                // Update vector database info if available
                if (data.vector_info) {
                    const vectorStatus = document.getElementById('pgvectorStatus');
                    const embeddingsCount = document.getElementById('embeddingsCount');

                    if (vectorStatus && embeddingsCount) {
                        // Set pgvector status
                        vectorStatus.textContent = data.vector_info.installed ? 'Installed' : 'Not Installed';
                        vectorStatus.classList.toggle('status-active', data.vector_info.installed);
                        vectorStatus.classList.toggle('status-inactive', !data.vector_info.installed);
                        setDashboardStatus(
                            dashboardVectorStatus,
                            data.vector_info.installed ? 'Installed' : 'Missing',
                            data.vector_info.installed
                        );

                        // Set embedding counts if available
                        if (data.vector_info.installed && 'with_embeddings' in data.vector_info) {
                            embeddingsCount.textContent = `${data.vector_info.with_embeddings}/${data.vector_info.with_embeddings + data.vector_info.without_embeddings}`;
                        } else {
                            embeddingsCount.textContent = 'N/A';
                        }
                    }
                }
            } else if (data.status === 'error') {
                // Handle error case
                console.warn("Database status unavailable:", data.message);

                // Add error message to UI if needed
                if (pgConnection && data.message) {
                    pgConnection.textContent = "Error";
                    pgConnection.classList.add('status-inactive');
                    pgConnection.title = data.message;
                    setDashboardStatus(dashboardDbStatus, 'Error', false);
                }
            }
        })
        .catch(error => {
            console.error('Error fetching database status:', error);
            // Update UI to show the error
            const pgConnection = document.getElementById('pg-connection');
            if (pgConnection) {
                pgConnection.textContent = "Error";
                pgConnection.classList.add('status-inactive');
                pgConnection.classList.remove('status-active');
                pgConnection.title = "Failed to fetch database status";
            }
            setDashboardStatus(dashboardDbStatus, 'Error', false);
        });
}

// Memory Configuration Management
function updateMemoryConfig() {
    fetch('/api/memory/config')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // Update UI with current memory configuration
                const config = data.config;

                // Update max messages
                const maxMessagesValue = document.getElementById('maxMessagesValue');
                maxMessagesValue.textContent = config.max_messages;

                // Update message window (context size)
                const messageWindowValue = document.getElementById('messageWindowValue');
                messageWindowValue.textContent = config.message_window;

                // Update max memory age
                const maxMemoryAgeValue = document.getElementById('maxMemoryAgeValue');
                maxMemoryAgeValue.textContent = config.max_memory_age;

                // Update enable context window toggle
                const enableContextWindowValue = document.getElementById('enableContextWindowValue');
                enableContextWindowValue.textContent = config.enable_context_window ? 'Enabled' : 'Disabled';

                // Update persist memory toggle
                const persistMemoryValue = document.getElementById('persistMemoryValue');
                persistMemoryValue.textContent = config.persist_memory ? 'Enabled' : 'Disabled';

                // Update MongoDB usage status
                const useMongoDBValue = document.getElementById('useMongoDBValue');
                useMongoDBValue.textContent = config.use_mongodb ? 'Yes' : 'No';

                // Update toggle button icons
                const toggleContextWindow = document.getElementById('toggleContextWindow');
                toggleContextWindow.innerHTML = config.enable_context_window ?
                    '<i class="fas fa-toggle-on"></i>' :
                    '<i class="fas fa-toggle-off"></i>';

                const togglePersistMemory = document.getElementById('togglePersistMemory');
                togglePersistMemory.innerHTML = config.persist_memory ?
                    '<i class="fas fa-toggle-on"></i>' :
                    '<i class="fas fa-toggle-off"></i>';
            }
        })
        .catch(error => {
            console.error('Error fetching memory configuration:', error);
        });
}

// Function to update a specific memory configuration setting
function updateMemorySetting(setting, value) {
    // Create payload with only the setting to update
    const payload = {};
    payload[setting] = value;

    fetch('/api/memory/config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            // Show success message
            addSystemMessage(`Memory setting '${setting}' updated to: ${value}`);

            // Update UI with new configuration
            updateMemoryConfig();
        } else {
            // Show error message
            addSystemMessage(`Error updating memory setting: ${data.message}`);
        }
    })
    .catch(error => {
        console.error('Error updating memory setting:', error);
        addSystemMessage('An error occurred while updating memory settings.');
    });
}

// Setup memory configuration UI controls
function setupMemoryConfigControls() {
    // Refresh button
    const refreshMemoryConfig = document.getElementById('refreshMemoryConfig');
    refreshMemoryConfig.addEventListener('click', updateMemoryConfig);

    // Edit max messages
    const editMaxMessages = document.getElementById('editMaxMessages');
    editMaxMessages.addEventListener('click', () => {
        const currentValue = document.getElementById('maxMessagesValue').textContent;
        const newValue = prompt('Enter maximum number of messages to store per conversation:', currentValue);
        if (newValue !== null && !isNaN(newValue) && newValue.trim() !== '') {
            updateMemorySetting('max_messages', parseInt(newValue));
        }
    });

    // Edit message window
    const editMessageWindow = document.getElementById('editMessageWindow');
    editMessageWindow.addEventListener('click', () => {
        const currentValue = document.getElementById('messageWindowValue').textContent;
        const newValue = prompt('Enter number of recent messages to use for context:', currentValue);
        if (newValue !== null && !isNaN(newValue) && newValue.trim() !== '') {
            updateMemorySetting('message_window', parseInt(newValue));
        }
    });

    // Edit max memory age
    const editMaxMemoryAge = document.getElementById('editMaxMemoryAge');
    editMaxMemoryAge.addEventListener('click', () => {
        const currentValue = document.getElementById('maxMemoryAgeValue').textContent;
        const newValue = prompt('Enter maximum age of memory in seconds:', currentValue);
        if (newValue !== null && !isNaN(newValue) && newValue.trim() !== '') {
            updateMemorySetting('max_memory_age', parseInt(newValue));
        }
    });

    // Toggle context window
    const toggleContextWindow = document.getElementById('toggleContextWindow');
    toggleContextWindow.addEventListener('click', () => {
        const currentValue = document.getElementById('enableContextWindowValue').textContent === 'Enabled';
        updateMemorySetting('enable_context_window', !currentValue);
    });

    // Toggle persist memory
    const togglePersistMemory = document.getElementById('togglePersistMemory');
    togglePersistMemory.addEventListener('click', () => {
        const currentValue = document.getElementById('persistMemoryValue').textContent === 'Enabled';
        updateMemorySetting('persist_memory', !currentValue);
    });
}

// Function to set up vector embeddings controls
function setupVectorEmbeddingsControls() {
    const updateEmbeddingsBtn = document.getElementById('updateEmbeddings');
    const forceUpdateEmbeddingsBtn = document.getElementById('forceUpdateEmbeddings');

    if (updateEmbeddingsBtn) {
        updateEmbeddingsBtn.addEventListener('click', () => {
            updateVectorEmbeddings(false);
        });
    }

    if (forceUpdateEmbeddingsBtn) {
        forceUpdateEmbeddingsBtn.addEventListener('click', () => {
            updateVectorEmbeddings(true);
        });
    }
}

// Function to update vector embeddings
function updateVectorEmbeddings(force = false) {
    if (isProcessing) {
        return;
    }

    // Confirm force update if necessary
    if (force && !confirm('This will overwrite ALL existing embeddings. Continue?')) {
        return;
    }

    // Set processing state
    isProcessing = true;
    showLoading();

    // Disable buttons
    const updateEmbeddingsBtn = document.getElementById('updateEmbeddings');
    const forceUpdateEmbeddingsBtn = document.getElementById('forceUpdateEmbeddings');
    if (updateEmbeddingsBtn) updateEmbeddingsBtn.disabled = true;
    if (forceUpdateEmbeddingsBtn) forceUpdateEmbeddingsBtn.disabled = true;

    // Add system message
    addSystemMessage(`${force ? 'Force updating' : 'Updating'} vector embeddings... This may take a while.`);

    // Send request to update embeddings
    fetch('/api/embeddings/update', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            force: force
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            // Calculate total updated count
            const itemCount = data.result?.item_embeddings?.updated_count || 0;
            const invoiceCount = data.result?.invoice_embeddings?.updated_count || 0;
            const totalCount = itemCount + invoiceCount;

            // Show success message
            addSystemMessage(`Successfully updated ${totalCount} embeddings (${itemCount} items, ${invoiceCount} invoices).`);

            // Update database counts to show the new embeddings
            updateDatabaseCounts();
        } else {
            addSystemMessage(`Error updating embeddings: ${data.message}`);
        }

        // Reset processing state
        isProcessing = false;
        hideLoading();

        // Re-enable buttons
        if (updateEmbeddingsBtn) updateEmbeddingsBtn.disabled = false;
        if (forceUpdateEmbeddingsBtn) forceUpdateEmbeddingsBtn.disabled = false;
    })
    .catch(error => {
        console.error('Error updating embeddings:', error);
        addSystemMessage(`Error updating embeddings: ${error.message}`);

        // Reset processing state
        isProcessing = false;
        hideLoading();

        // Re-enable buttons
        if (updateEmbeddingsBtn) updateEmbeddingsBtn.disabled = false;
        if (forceUpdateEmbeddingsBtn) forceUpdateEmbeddingsBtn.disabled = false;
    });
}

// Initialize UI when document is ready
function initUI() {
    // Initialize any UI elements that need setup
    updateSelectedUser();
    clearChatHistory();
    resetFileUpload();
}

function updateSelectedUser() {
    if (!whatsappNumberSelect || whatsappNumberSelect.options.length === 0) {
        setElementText(userIdDisplay, userId);
        return;
    }

    const selectedOption = whatsappNumberSelect.options[whatsappNumberSelect.selectedIndex];
    if (!selectedOption) {
        setElementText(userIdDisplay, userId);
        return;
    }

    whatsappNumber = selectedOption.value || whatsappNumber;
    if (selectedOption.dataset.userId) {
        userId = selectedOption.dataset.userId;
    }

    setElementText(userIdDisplay, userId);
}

function clearChatHistory() {
    if (!chatMessages || chatMessages.dataset.initialized === 'true') {
        return;
    }

    chatMessages.dataset.initialized = 'true';
}

function resetFileUpload() {
    if (fileInput) {
        fileInput.value = '';
    }
}

// Setup all event listeners
function setupEventListeners() {
    // Set up message form submission
    const messageForm = document.getElementById('messageForm');
    if (messageForm) {
        messageForm.addEventListener('submit', handleMessageSubmit);
    }

    // Set up file upload form submission
    const fileUploadForm = document.getElementById('fileUploadForm');
    if (fileUploadForm) {
        fileUploadForm.addEventListener('submit', handleFileUpload);
    }

    // Set up user selection change
    const userSelection = document.getElementById('userSelection');
    if (userSelection) {
        userSelection.addEventListener('change', handleUserChange);
    }
}

// Function to show create user dialog
function showCreateUserDialog() {
    // Create modal dialog
    const dialog = document.createElement('div');
    dialog.className = 'modal-dialog';

    // Create dialog content
    dialog.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h4>Create New User</h4>
                <button class="close-btn" id="closeDialog">×</button>
            </div>
            <div class="modal-body">
                <div class="form-group">
                    <label for="newWhatsappNumber">WhatsApp Number*:</label>
                    <input type="text" id="newWhatsappNumber" placeholder="+1234567890" required>
                </div>
                <div class="form-group">
                    <label for="newUserName">Name:</label>
                    <input type="text" id="newUserName" placeholder="User Name">
                </div>
                <div class="form-group">
                    <label for="newUserEmail">Email:</label>
                    <input type="email" id="newUserEmail" placeholder="user@example.com">
                </div>
            </div>
            <div class="modal-footer">
                <button class="action-btn" id="submitCreateUser">Create User</button>
                <button class="cancel-btn" id="cancelCreateUser">Cancel</button>
            </div>
        </div>
    `;

    // Add dialog to body
    document.body.appendChild(dialog);

    // Add event listeners
    document.getElementById('closeDialog').addEventListener('click', () => {
        document.body.removeChild(dialog);
    });

    document.getElementById('cancelCreateUser').addEventListener('click', () => {
        document.body.removeChild(dialog);
    });

    document.getElementById('submitCreateUser').addEventListener('click', () => {
        // Get form values
        const whatsappNumber = document.getElementById('newWhatsappNumber').value;
        const name = document.getElementById('newUserName').value;
        const email = document.getElementById('newUserEmail').value;

        // Validate WhatsApp number
        if (!whatsappNumber) {
            alert('WhatsApp number is required');
            return;
        }

        // Create user
        createUser(whatsappNumber, name, email);

        // Close dialog
        document.body.removeChild(dialog);
    });
}

// Function to create a new user
function createUser(whatsappNumber, name, email) {
    // Show loading
    showLoading();

    // Prepare request body
    const requestBody = {
        whatsapp_number: whatsappNumber
    };

    // Add optional fields if provided
    if (name) requestBody.name = name;
    if (email) requestBody.email = email;

    // Make API request
    fetch('/api/users/create', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody)
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            // Show success message
            addSystemMessage(`${data.message}: ${data.user.name} (${data.user.whatsapp_number})`);

            // Reload users
            loadUsers();

            // Select the new user
            setTimeout(() => {
                const select = document.getElementById('whatsappNumberSelect');
                const options = Array.from(select.options);
                const option = options.find(opt => opt.value === whatsappNumber);
                if (option) {
                    select.value = whatsappNumber;
                    // Trigger change event
                    const event = new Event('change');
                    select.dispatchEvent(event);
                }
            }, 500);
        } else {
            addSystemMessage(`Error creating user: ${data.message}`);
        }

        hideLoading();
    })
    .catch(error => {
        console.error('Error creating user:', error);
        addSystemMessage(`Error creating user: ${error.message}`);
        hideLoading();
        });
}

// Function to show company profile dialog
function showCompanyProfileModal() {
    // Get current user ID
    const userId = document.getElementById('userIdDisplay').textContent;

    if (!userId || userId === '0') {
        alert('Please select a user first');
        return;
    }

    // Show loading
    showLoading();

    // Fetch current profile data
    fetch(`/api/users/company-profile/${userId}`)
        .then(response => response.json())
        .then(data => {
            hideLoading();

            if (data.status === 'success') {
                // Current company data from preferences
                const prefs = data.preferences || {};

                // Create modal dialog
                const dialog = document.createElement('div');
                dialog.className = 'modal-dialog company-profile-modal';

                // Create dialog content
                dialog.innerHTML = `
                    <div class="modal-content">
                        <div class="modal-header">
                            <h4>Company Profile</h4>
                            <button class="close-btn" id="closeProfileDialog">×</button>
                        </div>
                        <div class="modal-body">
                            <div class="form-section">
                                <h5>Your Company Details</h5>
                                <div class="form-group">
                                    <label for="companyName">Company Name:</label>
                                    <input type="text" id="companyName" value="${prefs.company_name || ''}">
                                </div>
                                <div class="form-group">
                                    <label for="companyAddress">Company Address:</label>
                                    <textarea id="companyAddress" rows="3">${prefs.company_address || ''}</textarea>
                                </div>
                                <div class="form-group">
                                    <label for="companyPhone">Company Phone:</label>
                                    <input type="text" id="companyPhone" value="${prefs.company_phone || ''}">
                                </div>
                                <div class="form-group">
                                    <label for="companyEmail">Company Email:</label>
                                    <input type="email" id="companyEmail" value="${prefs.company_email || ''}">
                                </div>
                                <div class="form-group">
                                    <label for="companyWebsite">Company Website:</label>
                                    <input type="text" id="companyWebsite" value="${prefs.company_website || ''}">
                                </div>
                                <div class="form-group">
                                    <label for="paymentTerms">Payment Terms:</label>
                                    <input type="text" id="paymentTerms" value="${prefs.payment_terms || ''}"
                                           placeholder="e.g. Net 30 days">
                                </div>
                            </div>

                            <div class="form-section">
                                <h5>Last Client Information</h5>
                                <div class="form-hint">This information will be used as default for new invoices</div>
                                <div class="form-group">
                                    <label for="clientName">Client Name:</label>
                                    <input type="text" id="clientName" value="${prefs.client_name || ''}">
                                </div>
                                <div class="form-group">
                                    <label for="clientCompany">Client Company:</label>
                                    <input type="text" id="clientCompany" value="${prefs.client_company || ''}">
                                </div>
                                <div class="form-group">
                                    <label for="clientAddress">Client Address:</label>
                                    <textarea id="clientAddress" rows="3">${prefs.client_address || ''}</textarea>
                                </div>
                                <div class="form-group">
                                    <label for="clientPhone">Client Phone:</label>
                                    <input type="text" id="clientPhone" value="${prefs.client_phone || ''}">
                                </div>
                                <div class="form-group">
                                    <label for="clientEmail">Client Email:</label>
                                    <input type="email" id="clientEmail" value="${prefs.client_email || ''}">
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button class="action-btn" id="saveProfileBtn">Save Profile</button>
                            <button class="cancel-btn" id="cancelProfileBtn">Cancel</button>
                        </div>
                    </div>
                `;

                // Add dialog to body
                document.body.appendChild(dialog);

                // Add event listeners
                document.getElementById('closeProfileDialog').addEventListener('click', () => {
                    document.body.removeChild(dialog);
                });

                document.getElementById('cancelProfileBtn').addEventListener('click', () => {
                    document.body.removeChild(dialog);
                });

                document.getElementById('saveProfileBtn').addEventListener('click', () => {
                    // Collect form data
                    const formData = {
                        user_id: userId,
                        company_name: document.getElementById('companyName').value,
                        company_address: document.getElementById('companyAddress').value,
                        company_phone: document.getElementById('companyPhone').value,
                        company_email: document.getElementById('companyEmail').value,
                        company_website: document.getElementById('companyWebsite').value,
                        payment_terms: document.getElementById('paymentTerms').value,
                        client_name: document.getElementById('clientName').value,
                        client_company: document.getElementById('clientCompany').value,
                        client_address: document.getElementById('clientAddress').value,
                        client_phone: document.getElementById('clientPhone').value,
                        client_email: document.getElementById('clientEmail').value
                    };

                    // Save profile
                    saveCompanyProfile(formData);

                    // Close dialog
                    document.body.removeChild(dialog);
                });
            } else {
                alert(`Error loading profile: ${data.message}`);
            }
        })
        .catch(error => {
            hideLoading();
            console.error('Error loading company profile:', error);
            alert(`Error loading company profile: ${error.message}`);
        });
}

// Function to save company profile
function saveCompanyProfile(profileData) {
    // Show loading
    showLoading();

    // Make API request
    fetch('/api/users/company-profile', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(profileData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            // Show success message
            addSystemMessage(`Company profile updated successfully`);
        } else {
            addSystemMessage(`Error updating company profile: ${data.message}`);
        }

        hideLoading();
    })
    .catch(error => {
        console.error('Error saving company profile:', error);
        addSystemMessage(`Error saving company profile: ${error.message}`);
        hideLoading();
    });
}

// Replace the last bot message with a new one
function replaceLastBotMessage(newMessage) {
    const chatMessages = document.getElementById('chatMessages');
    const messages = chatMessages.querySelectorAll('.message:not(.user)');

    if (messages.length > 0) {
        const lastMessage = messages[messages.length - 1];

        // Update content
        const contentElement = lastMessage.querySelector('.message-content');
        contentElement.innerHTML = formatMessage(newMessage.content);

        // Update timestamp if needed
        const timestampElement = lastMessage.querySelector('.message-time');
        if (timestampElement) {
            timestampElement.textContent = formatMessageTime(newMessage.timestamp);
        }
    } else {
        // If no bot message exists, just add a new one
        addMessageToChat(newMessage);
    }
}

// Function to generate and download a DOCX invoice
function generateInvoice() {
    showLoading("Generating invoice document...");

    // First, get the company profile
    fetch('/api/users/company-profile', {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            // Use the company profile data to generate a DOCX invoice
            fetch('/api/generate-pdf-invoice', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    company_name: data.profile.company_name || 'Sample Company',
                    company_address: data.profile.company_address || '123 Business St',
                    company_phone: data.profile.company_phone || '555-1234',
                    company_email: data.profile.company_email || 'sample@company.com',
                    company_website: data.profile.company_website || 'www.samplecompany.com',
                    invoice_number: 'INV-' + Math.floor(Math.random() * 10000),
                    invoice_date: new Date().toISOString().split('T')[0],
                    due_date: new Date(Date.now() + 30*24*60*60*1000).toISOString().split('T')[0],
                    client_name: 'Sample Client',
                    client_address: '456 Client Ave',
                    client_phone: '555-5678',
                    client_email: 'client@example.com',
                    items: [
                        {
                            description: 'Service 1',
                            quantity: 1,
                            unit_price: 100,
                            amount: 100
                        },
                        {
                            description: 'Service 2',
                            quantity: 2,
                            unit_price: 50,
                            amount: 100
                        }
                    ],
                    subtotal: 200,
                    tax: 20,
                    total: 220,
                    notes: 'Thank you for your business!'
                })
            })
            .then(response => response.json())
            .then(result => {
                hideLoading();
                if (result.status === 'success') {
                    console.log('DOCX invoice generated successfully', result);

                    // Create a modal to show the download link
                    const modal = document.createElement('div');
                    modal.className = 'modal';
                    modal.innerHTML = `
                        <div class="modal-content">
                            <span class="close">&times;</span>
                            <h2>Invoice Generated Successfully</h2>
                            <div id="invoice-viewer">
                                <p>Your invoice document has been generated successfully.</p>
                                <div class="download-links">
                                    ${result.document_url ? `<a href="${result.document_url}" download class="btn btn-primary">Download Invoice Document</a>` : ''}
                                </div>
                            </div>
                        </div>
                    `;
                    document.body.appendChild(modal);

                    // Add event listener to close the modal
                    const closeBtn = modal.querySelector('.close');
                    closeBtn.onclick = function() {
                        document.body.removeChild(modal);
                    };

                    // Also close when clicking outside the modal content
                    modal.onclick = function(event) {
                        if (event.target === modal) {
                            document.body.removeChild(modal);
                        }
                    };

                    // Add some CSS for the modal
                    const style = document.createElement('style');
                    style.textContent = `
                        .modal {
                            display: block;
                            position: fixed;
                            z-index: 1000;
                            left: 0;
                            top: 0;
                            width: 100%;
                            height: 100%;
                            background-color: rgba(0,0,0,0.5);
                        }
                        .modal-content {
                            background-color: white;
                            margin: 10% auto;
                            padding: 20px;
                            border-radius: 8px;
                            width: 80%;
                            max-width: 800px;
                        }
                        .close {
                            color: #aaa;
                            float: right;
                            font-size: 28px;
                            font-weight: bold;
                            cursor: pointer;
                        }
                        .close:hover {
                            color: black;
                        }
                        .download-links {
                            margin-top: 20px;
                            display: flex;
                            gap: 10px;
                        }
                        .btn {
                            padding: 10px 15px;
                            border-radius: 5px;
                            text-decoration: none;
                            color: white;
                            font-weight: bold;
                        }
                        .btn-primary {
                            background-color: #4CAF50;
                        }
                    `;
                    document.head.appendChild(style);

                    // Add a reply in the chat
                    if (result.document_url) {
                        replaceLastBotMessage(`
                            <p>I've generated a sample invoice based on your company profile.</p>
                            <p><a href="${result.document_url}" download class="btn btn-primary">Download Invoice Document</a></p>
                        `);
                    } else {
                        replaceLastBotMessage(`
                            <p>I've generated a sample invoice based on your company profile, but the document generation failed. Please try again.</p>
                        `);
                    }
                } else {
                    console.error('Failed to generate invoice document', result);
                    replaceLastBotMessage(`
                        <p>Sorry, I couldn't generate the invoice document. Error: ${result.message || 'Unknown error'}</p>
                    `);
                }
            })
            .catch(error => {
                hideLoading();
                console.error('Error generating invoice document:', error);
                replaceLastBotMessage(`
                    <p>Sorry, there was an error generating the invoice document: ${error.message}</p>
                `);
            });
        } else {
            hideLoading();
            console.error('Failed to get company profile:', data);
            replaceLastBotMessage(`
                <p>Sorry, I couldn't retrieve your company profile. Please make sure your company profile is set up correctly.</p>
            `);
        }
    })
    .catch(error => {
        hideLoading();
        console.error('Error fetching company profile:', error);
        replaceLastBotMessage(`
            <p>Sorry, there was an error fetching your company profile: ${error.message}</p>
        `);
    });
}

// Function to add the PDF generation button to the navigation
function addPDFGenerationButton() {
    // Find the navigation container
    const navContainer = document.querySelector('.navbar-nav');

    if (navContainer) {
        // Create the button
        const button = document.createElement('button');
        button.className = 'btn btn-outline-success my-2 my-sm-0 ml-2';
        button.textContent = 'Generate Sample Invoice';

        // Add click event listener
        button.addEventListener('click', generateInvoice);

        // Create a list item to contain the button
        const listItem = document.createElement('li');
        listItem.className = 'nav-item';
        listItem.appendChild(button);

        // Add the button to the navigation
        navContainer.appendChild(listItem);
    }
}
