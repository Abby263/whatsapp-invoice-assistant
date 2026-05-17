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
const currentIntent = document.getElementById('currentIntent');
const workflowSteps = document.getElementById('workflowSteps');
const invoiceCount = document.getElementById('invoiceCount');
const itemCount = document.getElementById('itemCount');
const userIdDisplay = document.getElementById('userIdDisplay');
const userWhatsappDisplay = document.getElementById('userWhatsappDisplay');
const whatsappNumberSelect = document.getElementById('whatsappNumberSelect');
const fileStorageSection = document.getElementById('fileStorageSection');
const fileStorageKey = document.getElementById('fileStorageKey');
const fileStorageUrl = document.getElementById('fileStorageUrl');
const fileStorageUrlContainer = document.getElementById('fileStorageUrlContainer');
const dashboardReceiptCount = document.getElementById('dashboardReceiptCount');
const dashboardItemCount = document.getElementById('dashboardItemCount');
const dashboardIntent = document.getElementById('dashboardIntent');
const dashboardDbStatus = document.getElementById('dashboardDbStatus');
const dashboardStorageStatus = document.getElementById('dashboardStorageStatus');
const sidebarDbStatus = document.getElementById('sidebarDbStatus');
const sidebarDbDot = document.getElementById('sidebarDbDot');
const sidebarVectorStatus = document.getElementById('sidebarVectorStatus');
const sidebarVectorDot = document.getElementById('sidebarVectorDot');
const receiptsUserInvoices = document.getElementById('receiptsUserInvoices');
const receiptsUserItems = document.getElementById('receiptsUserItems');
const receiptsAllInvoices = document.getElementById('receiptsAllInvoices');
const receiptsEmbeddings = document.getElementById('receiptsEmbeddings');
const generatedInvoiceCount = document.getElementById('generatedInvoiceCount');
const generatedInvoiceValue = document.getElementById('generatedInvoiceValue');
const generatedInvoiceList = document.getElementById('generatedInvoiceList');
const generatedInvoiceEmpty = document.getElementById('generatedInvoiceEmpty');
const refreshGeneratedInvoicesBtn = document.getElementById('refreshGeneratedInvoicesBtn');
const generateInvoiceBtn = document.getElementById('generateInvoiceBtn');
const storageProvider = document.getElementById('storageProvider');
const themeToggleBtn = document.getElementById('themeToggleBtn');
const themeToggleIcon = document.getElementById('themeToggleIcon');
const sidebar = document.querySelector('.app-sidebar');
const sidebarToggle = document.getElementById('sidebarToggle');
const topbarTitle = document.getElementById('topbarTitle');
const topbarSubtitle = document.getElementById('topbarSubtitle');
const authSection = document.getElementById('authSection');
const authStatus = document.getElementById('authStatus');
const signInBtn = document.getElementById('signInBtn');
const linkWhatsappBtn = document.getElementById('linkWhatsappBtn');
const clerkUserButton = document.getElementById('clerkUserButton');
const topbarUser = document.getElementById('topbarUser');

// View metadata for topbar copy
const VIEW_META = {
    overview: {
        title: 'Overview',
        subtitle: 'Welcome back — here is the state of your receipt workspace.'
    },
    chat: {
        title: 'Chat',
        subtitle: 'Simulate WhatsApp conversations with the assistant.'
    },
    receipts: {
        title: 'Receipts',
        subtitle: 'Captured invoices, line items, and storage.'
    },
    inspector: {
        title: 'Workflow inspector',
        subtitle: 'LangGraph steps, intent, and token usage for the most recent message.'
    },
    settings: {
        title: 'Settings',
        subtitle: 'Users, memory, embeddings, and database health.'
    }
};

// Global variables
let isProcessing = false;
let conversationId = generateUUID();
let userId = "0";
let whatsappNumber = "";
let authState = {
    enabled: false,
    required: false,
    isSignedIn: false,
    needsLink: false,
    user: null
};
const nativeFetch = window.fetch.bind(window);

function setElementText(element, value) {
    if (element) {
        element.textContent = value;
    }
}

function setWhatsappLinkState(state) {
    if (topbarUser) {
        topbarUser.dataset.linkState = state;
    }
}

function setWhatsappUnlinked(label = 'Link WhatsApp') {
    whatsappNumber = '';
    userId = '0';
    setWhatsappLinkState('unlinked');
    setElementText(userWhatsappDisplay, 'Not linked');
    setElementText(userIdDisplay, userId || '0');

    if (whatsappNumberSelect) {
        whatsappNumberSelect.innerHTML = '';
        const option = document.createElement('option');
        option.value = '';
        option.textContent = label;
        whatsappNumberSelect.appendChild(option);
        whatsappNumberSelect.value = '';
        whatsappNumberSelect.disabled = true;
    }
}

function normalizeUiWhatsappNumber(value) {
    const normalized = (value || '').trim();
    return normalized === '+1234567890' ? '' : normalized;
}

function setActiveWhatsappUser(user) {
    if (!user) {
        setWhatsappUnlinked();
        return;
    }

    const number = normalizeUiWhatsappNumber(user.whatsapp_number);
    if (!number) {
        setWhatsappUnlinked();
        return;
    }

    userId = user.id || userId || '0';
    whatsappNumber = number;
    setWhatsappLinkState('linked');
    setElementText(userIdDisplay, userId);
    setElementText(userWhatsappDisplay, whatsappNumber);

    if (whatsappNumberSelect) {
        whatsappNumberSelect.disabled = false;
        const existingOption = Array.from(whatsappNumberSelect.options).find(
            option => option.value === whatsappNumber
        );
        const option = existingOption || document.createElement('option');
        option.value = whatsappNumber;
        option.textContent = `${user.name || 'Linked user'} (${whatsappNumber})`;
        option.dataset.userId = userId;
        if (!existingOption) {
            if (
                whatsappNumberSelect.options.length === 1 &&
                !whatsappNumberSelect.options[0].value
            ) {
                whatsappNumberSelect.innerHTML = '';
            }
            whatsappNumberSelect.appendChild(option);
        }
        whatsappNumberSelect.value = whatsappNumber;
    }
}

function preserveActiveWhatsappSelection(reason = '') {
    if (!whatsappNumber) {
        return false;
    }

    authState.needsLink = false;
    setWhatsappLinkState('linked');
    setElementText(userIdDisplay, userId || '0');
    setElementText(userWhatsappDisplay, whatsappNumber);

    if (whatsappNumberSelect) {
        whatsappNumberSelect.disabled = false;
        const existingOption = Array.from(whatsappNumberSelect.options).find(
            option => option.value === whatsappNumber
        );
        if (!existingOption) {
            const option = document.createElement('option');
            option.value = whatsappNumber;
            option.textContent = `Linked user (${whatsappNumber})`;
            option.dataset.userId = userId || '0';
            whatsappNumberSelect.innerHTML = '';
            whatsappNumberSelect.appendChild(option);
        }
        whatsappNumberSelect.value = whatsappNumber;
    }

    updateWorkspaceAuthAvailability();
    if (reason) {
        console.warn(`Preserved linked WhatsApp selection after stale response: ${reason}`);
    }
    return true;
}

function setDashboardStatus(element, value, active = true) {
    if (!element) {
        return;
    }

    element.textContent = value;
    element.classList.toggle('status-active', active);
    element.classList.toggle('status-inactive', !active);
}

function setSidebarStatus(textEl, dotEl, value, active) {
    if (textEl) {
        textEl.textContent = value;
    }
    if (dotEl) {
        dotEl.classList.toggle('is-good', active === true);
        dotEl.classList.toggle('is-bad', active === false);
        dotEl.classList.toggle('is-warn', active === null || active === undefined);
    }
}

function updateFileStorageInfo(storage) {
    if (!storage || Object.keys(storage).length === 0) {
        return;
    }

    fileStorageSection.style.display = 'block';
    const provider = storage.provider || 'Supabase';
    setElementText(storageProvider, provider);
    fileStorageKey.textContent = storage.file_key || storage.path || 'None';
    setElementText(dashboardStorageStatus, `${provider} ready`);

    if (storage.url) {
        fileStorageUrl.href = storage.url;
        fileStorageUrl.textContent = 'View File';
        fileStorageUrlContainer.style.display = 'block';
    } else {
        fileStorageUrl.href = '#';
        fileStorageUrl.textContent = 'None';
    }
}

function setupAuthenticatedFetch() {
    window.fetch = async (input, init = {}) => {
        const requestUrl = typeof input === 'string' ? input : input.url || input.toString();
        const url = new URL(requestUrl, window.location.origin);
        const isAppApi = url.origin === window.location.origin && url.pathname.startsWith('/api/');

        if (!isAppApi || !window.Clerk || !window.Clerk.session) {
            return nativeFetch(input, init);
        }

        try {
            const token = await window.Clerk.session.getToken();
            if (!token) {
                return nativeFetch(input, init);
            }

            const headers = new Headers(
                init.headers || (input instanceof Request ? input.headers : undefined)
            );
            headers.set('Authorization', `Bearer ${token}`);
            return nativeFetch(input, {
                ...init,
                headers
            });
        } catch (error) {
            console.warn('Could not attach Clerk token to request:', error);
            return nativeFetch(input, init);
        }
    };
}

function deriveClerkDomain(publishableKey) {
    try {
        const encoded = publishableKey.split('_').slice(2).join('_');
        const normalized = encoded.replace(/-/g, '+').replace(/_/g, '/');
        const padded = normalized.padEnd(
            normalized.length + ((4 - (normalized.length % 4)) % 4),
            '='
        );
        const decoded = atob(padded);
        return decoded.replace(/\$$/, '');
    } catch (error) {
        console.error('Could not derive Clerk Frontend API domain:', error);
        return null;
    }
}

function loadScript(src, attributes = {}) {
    return new Promise((resolve, reject) => {
        const existing = Array.from(document.scripts).find(script => script.src === src);
        if (existing) {
            resolve();
            return;
        }

        const script = document.createElement('script');
        script.src = src;
        script.async = true;
        script.crossOrigin = 'anonymous';
        Object.entries(attributes).forEach(([key, value]) => {
            script.setAttribute(key, value);
        });
        script.onload = resolve;
        script.onerror = () => reject(new Error(`Failed to load ${src}`));
        document.head.appendChild(script);
    });
}

async function setupAuth() {
    if (!authSection) {
        return;
    }

    let configResponse;
    try {
        configResponse = await nativeFetch('/api/auth/config');
    } catch (error) {
        console.warn('Auth config unavailable:', error);
        setAuthUiState('disabled', 'Auth offline');
        return;
    }

    const configData = await configResponse.json();
    const authConfig = configData.auth || {};
    authState.enabled = !!authConfig.enabled;
    authState.required = !!authConfig.required;

    if (!authState.enabled || !authConfig.publishable_key) {
        setAuthUiState('disabled', 'Auth optional');
        return;
    }

    const clerkDomain = deriveClerkDomain(authConfig.publishable_key);
    if (!clerkDomain) {
        setAuthUiState('disabled', 'Auth misconfigured');
        updateWorkspaceAuthAvailability();
        return;
    }

    try {
        await loadScript(`https://${clerkDomain}/npm/@clerk/ui@1/dist/ui.browser.js`);
        await loadScript(
            `https://${clerkDomain}/npm/@clerk/clerk-js@6/dist/clerk.browser.js`,
            {'data-clerk-publishable-key': authConfig.publishable_key}
        );

        await window.Clerk.load({
            ui: { ClerkUI: window.__internal_ClerkUICtor },
        });
    } catch (error) {
        console.error('Clerk failed to load:', error);
        setAuthUiState('signed-out', 'Auth unavailable');
        updateWorkspaceAuthAvailability();
        return;
    }

    if (signInBtn) {
        signInBtn.addEventListener('click', () => {
            window.Clerk.openSignIn();
        });
    }

    if (linkWhatsappBtn) {
        linkWhatsappBtn.addEventListener('click', linkAuthenticatedWhatsappNumber);
    }

    if (typeof window.Clerk.addListener === 'function') {
        window.Clerk.addListener(({ user }) => {
            if (user && !authState.isSignedIn) {
                handleSignedInUser();
            } else if (!user && authState.isSignedIn) {
                authState.isSignedIn = false;
                authState.needsLink = false;
                authState.user = null;
                setWhatsappUnlinked();
                setAuthUiState('signed-out', 'Sign in required');
                updateWorkspaceAuthAvailability();
            }
        });
    }

    if (window.Clerk.isSignedIn) {
        await handleSignedInUser();
    } else {
        setAuthUiState('signed-out', 'Sign in required');
        updateWorkspaceAuthAvailability();
    }
}

async function handleSignedInUser() {
    authState.isSignedIn = true;
    authState.needsLink = false;
    authState.user = window.Clerk.user || null;
    updateWorkspaceAuthAvailability();

    if (clerkUserButton && window.Clerk.mountUserButton) {
        clerkUserButton.innerHTML = '';
        window.Clerk.mountUserButton(clerkUserButton);
    }

    try {
        const user = authState.user;
        const response = await fetch('/api/auth/sync', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(getClerkProfilePayload(user))
        });
        const data = await response.json();
        const linkedUser = data.linked_user || data.identity?.linked_user;

        if (linkedUser) {
            applyLinkedUser(linkedUser);
            setAuthUiState('signed-in', 'Signed in');
        } else {
            authState.needsLink = true;
            setAuthUiState('needs-link', 'Link WhatsApp');
            updateWorkspaceAuthAvailability();
            addSystemMessage('Sign-in complete. Link your WhatsApp number so web and WhatsApp receipts use the same account.');
        }
    } catch (error) {
        console.error('Error syncing Clerk user:', error);
        authState.needsLink = true;
        setAuthUiState('needs-link', 'Sync needed');
        updateWorkspaceAuthAvailability();
    }
}

function getClerkProfilePayload(user) {
    const primaryEmail = user?.primaryEmailAddress?.emailAddress || '';
    const fullName = user?.fullName || [user?.firstName, user?.lastName].filter(Boolean).join(' ');
    const primaryPhone = user?.primaryPhoneNumber?.phoneNumber || '';

    return {
        email: primaryEmail,
        name: fullName,
        whatsapp_number: primaryPhone || whatsappNumber || '',
    };
}

async function linkAuthenticatedWhatsappNumber() {
    if (!window.Clerk || !window.Clerk.isSignedIn) {
        if (window.Clerk) {
            window.Clerk.openSignIn();
        }
        return;
    }

    const user = authState.user || window.Clerk.user;
    const defaultNumber = user?.primaryPhoneNumber?.phoneNumber || whatsappNumber || '';
    const linkedNumber = prompt('Enter the WhatsApp number used for receipt uploads:', defaultNumber);
    if (!linkedNumber) {
        return;
    }

    showLoading('Linking WhatsApp number...');
    try {
        const response = await fetch('/api/auth/link-whatsapp', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                ...getClerkProfilePayload(user),
                whatsapp_number: linkedNumber.trim()
            })
        });
        const data = await response.json();

        if (data.status === 'success' && data.user) {
            applyLinkedUser(data.user);
            setAuthUiState('signed-in', 'Signed in');
            addSystemMessage(`Linked this workspace to WhatsApp number ${data.user.whatsapp_number}.`);
            initializeApp();
            loadUsers();
            updateDatabaseCounts();
        } else {
            addSystemMessage(`Could not link WhatsApp number: ${data.message}`);
        }
    } catch (error) {
        console.error('Error linking WhatsApp number:', error);
        addSystemMessage(`Could not link WhatsApp number: ${error.message}`);
    } finally {
        hideLoading();
    }
}

function applyLinkedUser(linkedUser) {
    if (!linkedUser) {
        return;
    }

    authState.needsLink = false;
    setActiveWhatsappUser(linkedUser);

    updateWorkspaceAuthAvailability();
    loadGeneratedInvoices();
}

function setAuthUiState(state, label) {
    if (authSection) {
        authSection.dataset.authState = state;
    }
    if (authStatus) {
        authStatus.textContent = label;
    }
}

function updateWorkspaceAuthAvailability() {
    const shouldDisable = authState.required && (!authState.isSignedIn || authState.needsLink);

    [sendBtn, attachBtn, messageInput].forEach(element => {
        if (element) {
            element.disabled = shouldDisable;
        }
    });
}

// Initialize application
document.addEventListener('DOMContentLoaded', async () => {
    setupTheme();
    setupNavigation();
    setupAuthenticatedFetch();
    setWhatsappUnlinked();
    await setupAuth();

    const canLoadWorkspace = (
        !authState.enabled ||
        !authState.required ||
        (authState.isSignedIn && !authState.needsLink)
    );
    if (canLoadWorkspace) {
        initializeApp();
        updateDatabaseCounts();
        loadGeneratedInvoices();
        loadUsers();
    } else {
        addSystemMessage('Sign in to connect your WhatsApp receipts with this workspace.');
    }

    if (!whatsappNumber) {
        setWhatsappUnlinked(authState.needsLink ? 'Link WhatsApp' : 'No user selected');
    }

    // Setup WhatsApp number select event handling
    if (whatsappNumberSelect) {
        whatsappNumberSelect.addEventListener('change', switchUser);
    }

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

    if (refreshGeneratedInvoicesBtn) {
        refreshGeneratedInvoicesBtn.addEventListener('click', loadGeneratedInvoices);
    }

    if (generateInvoiceBtn) {
        generateInvoiceBtn.addEventListener('click', showGeneratedInvoiceModal);
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

function setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item[data-view]');
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            switchView(item.dataset.view);
            if (sidebar) sidebar.classList.remove('is-open');
        });
    });

    document.querySelectorAll('[data-goto]').forEach(btn => {
        btn.addEventListener('click', () => {
            switchView(btn.dataset.goto);
        });
    });

    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', () => {
            sidebar.classList.toggle('is-open');
        });
    }
}

function switchView(viewName) {
    if (!viewName) return;

    document.querySelectorAll('.view').forEach(view => {
        view.classList.toggle('is-active', view.dataset.view === viewName);
    });

    document.querySelectorAll('.nav-item[data-view]').forEach(item => {
        item.classList.toggle('is-active', item.dataset.view === viewName);
    });

    const meta = VIEW_META[viewName];
    if (meta) {
        if (topbarTitle) topbarTitle.textContent = meta.title;
        if (topbarSubtitle) topbarSubtitle.textContent = meta.subtitle;
    }

    if (viewName === 'chat' && messageInput) {
        setTimeout(() => messageInput.focus(), 50);
    }
}

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

    if (themeToggleBtn) {
        themeToggleBtn.setAttribute(
            'aria-label',
            normalizedTheme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'
        );
        themeToggleBtn.setAttribute(
            'title',
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

    document.querySelectorAll('[data-generate-invoice]').forEach(button => {
        if (button.dataset.bound === 'true') {
            return;
        }

        button.dataset.bound = 'true';
        button.addEventListener('click', showGeneratedInvoiceModal);
    });
}

// Function to load users into the dropdown
function loadUsers() {
    if (!whatsappNumberSelect) {
        return;
    }

    fetch('/api/users')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success' && Array.isArray(data.users)) {
                const currentValue = whatsappNumberSelect.value;
                const users = data.users.filter(user => normalizeUiWhatsappNumber(user.whatsapp_number));

                if (data.needs_link || users.length === 0) {
                    if (preserveActiveWhatsappSelection('users response had no linked users')) {
                        return;
                    }
                    setWhatsappUnlinked(data.needs_link ? 'Link WhatsApp' : 'No user selected');
                    updateWorkspaceAuthAvailability();
                    return;
                }

                whatsappNumberSelect.innerHTML = '';

                users.forEach(user => {
                    const option = document.createElement('option');
                    const number = normalizeUiWhatsappNumber(user.whatsapp_number);
                    option.value = number;
                    option.textContent = `${user.name || 'Linked user'} (${number})`;
                    option.dataset.userId = user.id;
                    whatsappNumberSelect.appendChild(option);
                });

                const selectedUser = (
                    users.find(user => normalizeUiWhatsappNumber(user.whatsapp_number) === currentValue)
                    || users[0]
                );
                setActiveWhatsappUser(selectedUser);
                updateDatabaseCounts();
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
    if (!newWhatsappNumber) {
        setWhatsappUnlinked();
        return;
    }

    // Get the user ID from the selected option
    const selectedOption = whatsappNumberSelect.options[whatsappNumberSelect.selectedIndex];
    const newUserId = selectedOption?.dataset.userId;

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
    if (!whatsappNumber) {
        setWhatsappUnlinked();
        return;
    }

    showLoading();

    fetch(`/api/init?whatsapp_number=${encodeURIComponent(whatsappNumber)}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                if (data.needs_link) {
                    if (preserveActiveWhatsappSelection('initialize-for-user response required linking')) {
                        hideLoading();
                        return;
                    }
                    setWhatsappUnlinked('Link WhatsApp');
                    addSystemMessage('Link your WhatsApp number before loading receipts.');
                    hideLoading();
                    return;
                }

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
                loadGeneratedInvoices();
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

                if (data.needs_link) {
                    if (preserveActiveWhatsappSelection('init response required linking')) {
                        return;
                    }
                    authState.needsLink = true;
                    setWhatsappUnlinked('Link WhatsApp');
                    updateWorkspaceAuthAvailability();
                    return;
                }

                if (data.user_id && normalizeUiWhatsappNumber(data.whatsapp_number)) {
                    setActiveWhatsappUser({
                        id: data.user_id,
                        name: data.user_name || 'Linked user',
                        whatsapp_number: data.whatsapp_number
                    });
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
    if (authState.required && !whatsappNumber) {
        addSystemMessage('Link your WhatsApp number before using the workspace.');
        return;
    }
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
            if (data.generated_invoice || data.metadata?.generated_invoice) {
                loadGeneratedInvoices();
            }

            // Update user information display if provided
            if (data.user_id) {
                userId = data.user_id;
                userIdDisplay.textContent = userId;
            }

            if (data.whatsapp_number) {
                setActiveWhatsappUser({
                    id: data.user_id || userId,
                    name: data.user_name || 'Linked user',
                    whatsapp_number: data.whatsapp_number
                });
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
    if (authState.required && !whatsappNumber) {
        addSystemMessage('Link your WhatsApp number before uploading receipts.');
        fileInput.value = '';
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
                setActiveWhatsappUser({
                    id: data.user_id || userId,
                    name: data.user_name || 'Linked user',
                    whatsapp_number: data.whatsapp_number
                });
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
                const storage = storageData.file_storage;
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
                    setActiveWhatsappUser({
                        id: flowData.user_id || userId,
                        name: flowData.user_name || 'Linked user',
                        whatsapp_number: flowData.whatsapp_number
                    });
                }

                const flowStorage = flowData.file_storage;
                if (flowStorage && Object.keys(flowStorage).length > 0 && fileStorageSection.style.display !== 'block') {
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
                const stepStorage = data.file_storage;
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
                    const fileStorageInfoSection = document.createElement('div');
                    fileStorageInfoSection.className = 'storage-info-section';
                    fileStorageInfoSection.innerHTML = `
                        <h4>File Storage Information</h4>
                        <div class="file-storage-info">
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
                    modalBody.appendChild(fileStorageInfoSection);
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
                        setSidebarStatus(sidebarDbStatus, sidebarDbDot, 'Online', true);
                    } else {
                        pgConnection.textContent = "Not Connected";
                        pgConnection.classList.add('status-inactive');
                        pgConnection.classList.remove('status-active');
                        setDashboardStatus(dashboardDbStatus, 'Offline', false);
                        setSidebarStatus(sidebarDbStatus, sidebarDbDot, 'Offline', false);

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

                const totalInvoices = data.counts.invoices.total || 0;
                const userInvoices = data.counts.invoices.user_specific || 0;
                const totalItems = data.counts.items || 0;
                const userItems = data.counts.user_items || 0;

                if (dbInvoicesCount) {
                    dbInvoicesCount.textContent = totalInvoices;
                }

                if (dbUserInvoicesCount) {
                    dbUserInvoicesCount.textContent = userInvoices;
                }

                setElementText(dashboardReceiptCount, userInvoices);
                setElementText(receiptsUserInvoices, userInvoices);
                setElementText(receiptsAllInvoices, totalInvoices);

                if (dbItemsCount) {
                    dbItemsCount.textContent = totalItems;
                }

                if (dbUserItemsCount) {
                    dbUserItemsCount.textContent = userItems;
                }

                setElementText(dashboardItemCount, userItems);
                setElementText(receiptsUserItems, userItems);

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
                    const isInstalled = !!data.vector_info.installed;

                    if (vectorStatus) {
                        vectorStatus.textContent = isInstalled ? 'Installed' : 'Not Installed';
                        vectorStatus.classList.toggle('status-active', isInstalled);
                        vectorStatus.classList.toggle('status-inactive', !isInstalled);
                    }

                    setSidebarStatus(
                        sidebarVectorStatus,
                        sidebarVectorDot,
                        isInstalled ? 'Online' : 'Missing',
                        isInstalled
                    );

                    // Set embedding counts if available
                    let embeddingDisplay = 'N/A';
                    if (isInstalled && 'with_embeddings' in data.vector_info) {
                        embeddingDisplay = `${data.vector_info.with_embeddings}/${data.vector_info.with_embeddings + data.vector_info.without_embeddings}`;
                    }
                    if (embeddingsCount) {
                        embeddingsCount.textContent = embeddingDisplay;
                    }
                    setElementText(receiptsEmbeddings, embeddingDisplay);
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
                    setSidebarStatus(sidebarDbStatus, sidebarDbDot, 'Error', false);
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
            setSidebarStatus(sidebarDbStatus, sidebarDbDot, 'Error', false);
        });
}

function loadGeneratedInvoices() {
    if (!generatedInvoiceList) {
        return;
    }

    fetch(`/api/generated-invoices?user_id=${userId}`)
        .then(response => response.json())
        .then(data => {
            if (data.status !== 'success') {
                console.warn('Generated invoices unavailable:', data.message);
                return;
            }
            renderGeneratedInvoices(data.generated_invoices || data.invoices || []);
            const analytics = data.analytics || {};
            setElementText(generatedInvoiceCount, analytics.count || 0);
            setElementText(
                generatedInvoiceValue,
                formatGeneratedCurrency(analytics.total_amount || 0, 'USD')
            );
        })
        .catch(error => {
            console.error('Error loading generated invoices:', error);
        });
}

function showGeneratedInvoiceModal() {
    if (!userId || userId === '0') {
        alert('Please select or link a user before generating an invoice.');
        return;
    }

    showLoading('Loading invoice defaults...');
    fetch(`/api/users/company-profile/${encodeURIComponent(userId)}`)
        .then(response => response.json())
        .then(data => {
            hideLoading();
            const prefs = data.status === 'success' ? (data.preferences || data.profile || {}) : {};
            renderGeneratedInvoiceModal(prefs);
        })
        .catch(error => {
            hideLoading();
            console.warn('Could not load invoice defaults:', error);
            renderGeneratedInvoiceModal({});
        });
}

function renderGeneratedInvoiceModal(prefs = {}) {
    const dialog = document.createElement('div');
    dialog.className = 'modal-dialog generated-invoice-modal';
    const dueDate = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];

    dialog.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h4>Generate Invoice</h4>
                <button class="close-btn" id="closeGeneratedInvoiceDialog" type="button">×</button>
            </div>
            <div class="modal-body">
                <div class="form-section">
                    <h5>Seller defaults</h5>
                    <div class="form-grid-2">
                        <div class="form-group">
                            <label for="invoiceCompanyName">Company name</label>
                            <input type="text" id="invoiceCompanyName" value="${escapeAttribute(prefs.company_name || '')}" placeholder="Your company">
                        </div>
                        <div class="form-group">
                            <label for="invoiceCompanyEmail">Company email</label>
                            <input type="email" id="invoiceCompanyEmail" value="${escapeAttribute(prefs.company_email || '')}" placeholder="billing@company.com">
                        </div>
                    </div>
                    <div class="form-grid-2">
                        <div class="form-group">
                            <label for="invoiceCurrency">Currency</label>
                            <select id="invoiceCurrency">
                                ${['USD', 'INR', 'EUR', 'GBP', 'CAD', 'AUD'].map(currency => (
                                    `<option value="${currency}" ${String(prefs.currency || 'USD').toUpperCase() === currency ? 'selected' : ''}>${currency}</option>`
                                )).join('')}
                            </select>
                        </div>
                        <div class="form-group">
                            <label for="invoicePaymentTerms">Payment terms</label>
                            <input type="text" id="invoicePaymentTerms" value="${escapeAttribute(prefs.payment_terms || '')}" placeholder="Net 30">
                        </div>
                    </div>
                </div>

                <div class="form-section">
                    <h5>Client</h5>
                    <div class="form-grid-2">
                        <div class="form-group">
                            <label for="invoiceClientName">Client name</label>
                            <input type="text" id="invoiceClientName" value="${escapeAttribute(prefs.client_name || '')}" placeholder="Primary contact">
                        </div>
                        <div class="form-group">
                            <label for="invoiceClientCompany">Client company</label>
                            <input type="text" id="invoiceClientCompany" value="${escapeAttribute(prefs.client_company || '')}" placeholder="Client LLC">
                        </div>
                    </div>
                    <div class="form-grid-2">
                        <div class="form-group">
                            <label for="invoiceClientEmail">Client email</label>
                            <input type="email" id="invoiceClientEmail" value="${escapeAttribute(prefs.client_email || '')}" placeholder="client@example.com">
                        </div>
                        <div class="form-group">
                            <label for="invoiceDueDate">Due date</label>
                            <input type="date" id="invoiceDueDate" value="${escapeAttribute(dueDate)}">
                        </div>
                    </div>
                    <div class="form-group">
                        <label for="invoiceClientAddress">Client address</label>
                        <textarea id="invoiceClientAddress" rows="2" placeholder="Billing address">${escapeHtml(prefs.client_address || '')}</textarea>
                    </div>
                </div>

                <div class="form-section">
                    <h5>Transaction</h5>
                    <div class="form-group">
                        <label for="invoiceLineDescription">Description</label>
                        <input type="text" id="invoiceLineDescription" placeholder="Consulting services, product delivery, project milestone" required>
                    </div>
                    <div class="form-grid-2">
                        <div class="form-group">
                            <label for="invoiceQuantity">Quantity</label>
                            <input type="number" id="invoiceQuantity" min="0.01" step="0.01" value="1">
                        </div>
                        <div class="form-group">
                            <label for="invoiceUnitPrice">Unit price</label>
                            <input type="number" id="invoiceUnitPrice" min="0" step="0.01" placeholder="0.00" required>
                        </div>
                    </div>
                    <div class="form-grid-2">
                        <div class="form-group">
                            <label for="invoiceTaxRate">Tax rate %</label>
                            <input type="number" id="invoiceTaxRate" min="0" step="0.01" value="${escapeAttribute(prefs.tax_rate || 0)}">
                        </div>
                        <div class="form-group">
                            <label for="invoiceNotes">Notes</label>
                            <input type="text" id="invoiceNotes" value="${escapeAttribute(prefs.payment_instructions || '')}" placeholder="Payment instructions or memo">
                        </div>
                    </div>
                    <label class="checkbox-row" for="invoiceSaveDefaults">
                        <input type="checkbox" id="invoiceSaveDefaults" checked>
                        <span>
                            Save seller, client, currency, tax, and payment terms as defaults for future WhatsApp and web invoices.
                        </span>
                    </label>
                </div>
            </div>
            <div class="modal-footer">
                <button class="action-btn" id="submitGeneratedInvoice" type="button">Generate Invoice</button>
                <button class="cancel-btn" id="cancelGeneratedInvoice" type="button">Cancel</button>
            </div>
        </div>
    `;

    document.body.appendChild(dialog);

    const closeDialog = () => {
        if (document.body.contains(dialog)) {
            document.body.removeChild(dialog);
        }
    };

    document.getElementById('closeGeneratedInvoiceDialog').addEventListener('click', closeDialog);
    document.getElementById('cancelGeneratedInvoice').addEventListener('click', closeDialog);
    dialog.addEventListener('click', event => {
        if (event.target === dialog) {
            closeDialog();
        }
    });
    document.getElementById('submitGeneratedInvoice').addEventListener('click', () => {
        submitGeneratedInvoice(dialog, closeDialog);
    });
}

function submitGeneratedInvoice(dialog, closeDialog) {
    const description = document.getElementById('invoiceLineDescription').value.trim();
    const unitPrice = Number(document.getElementById('invoiceUnitPrice').value || 0);
    const quantity = Number(document.getElementById('invoiceQuantity').value || 1);

    if (!description || !unitPrice || unitPrice < 0 || !quantity || quantity <= 0) {
        alert('Enter a transaction description, quantity, and unit price.');
        return;
    }

    const submitBtn = document.getElementById('submitGeneratedInvoice');
    submitBtn.disabled = true;
    showLoading('Generating invoice...');

    const payload = {
        user_id: userId,
        source: 'web',
        save_defaults: document.getElementById('invoiceSaveDefaults').checked,
        company_name: document.getElementById('invoiceCompanyName').value.trim(),
        company_email: document.getElementById('invoiceCompanyEmail').value.trim(),
        currency: document.getElementById('invoiceCurrency').value,
        payment_terms: document.getElementById('invoicePaymentTerms').value.trim(),
        client_name: document.getElementById('invoiceClientName').value.trim(),
        client_company: document.getElementById('invoiceClientCompany').value.trim(),
        client_email: document.getElementById('invoiceClientEmail').value.trim(),
        client_address: document.getElementById('invoiceClientAddress').value.trim(),
        due_date: document.getElementById('invoiceDueDate').value,
        tax_rate: Number(document.getElementById('invoiceTaxRate').value || 0),
        notes: document.getElementById('invoiceNotes').value.trim(),
        items: [
            {
                description,
                quantity,
                unit_price: unitPrice,
                total_price: quantity * unitPrice
            }
        ]
    };

    fetch('/api/generated-invoices', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
    })
        .then(response => response.json())
        .then(data => {
            if (data.status !== 'success') {
                throw new Error(data.message || 'Invoice generation failed');
            }

            closeDialog();
            const invoice = data.generated_invoice || data.invoice || {};
            addSystemMessage(`Generated invoice ${escapeHtml(invoice.invoice_number || '')}. It is now saved under this user.`);
            loadGeneratedInvoices();
            updateDatabaseCounts();
            switchView('receipts');
        })
        .catch(error => {
            console.error('Error generating invoice:', error);
            addSystemMessage(`Could not generate invoice: ${escapeHtml(error.message)}`);
        })
        .finally(() => {
            hideLoading();
            if (document.body.contains(dialog)) {
                submitBtn.disabled = false;
            }
        });
}

function renderGeneratedInvoices(invoices) {
    if (!generatedInvoiceList) {
        return;
    }

    generatedInvoiceList.innerHTML = '';
    if (!invoices.length) {
        if (generatedInvoiceEmpty) {
            generatedInvoiceList.appendChild(generatedInvoiceEmpty);
            generatedInvoiceEmpty.style.display = 'grid';
        }
        return;
    }

    invoices.forEach(invoice => {
        const row = document.createElement('article');
        row.className = 'generated-invoice-row';
        const client = invoice.client_name || invoice.client_company || 'Client';
        const amount = formatGeneratedCurrency(invoice.total_amount || 0, invoice.currency || 'USD');
        const created = invoice.created_at ? new Date(invoice.created_at).toLocaleDateString() : 'Recent';
        const downloadUrl = invoice.pdf_url || invoice.document_url || '#';
        const downloadLabel = invoice.pdf_url ? 'PDF' : 'File';

        row.innerHTML = `
            <div class="generated-invoice-main">
                <strong>${escapeHtml(invoice.invoice_number || `Invoice #${invoice.id}`)}</strong>
                <span>${escapeHtml(client)} · ${escapeHtml(invoice.status || 'generated')}</span>
            </div>
            <div class="generated-invoice-meta">
                <strong>${amount}</strong>
                <span>${created}</span>
            </div>
            <div class="generated-invoice-actions">
                ${downloadUrl !== '#'
                    ? `<a href="${escapeAttribute(downloadUrl)}" target="_blank" rel="noopener"><i class="fas fa-download"></i>${downloadLabel}</a>`
                    : '<span class="muted">No file</span>'}
            </div>
        `;
        generatedInvoiceList.appendChild(row);
    });
}

function formatGeneratedCurrency(amount, currency) {
    try {
        return new Intl.NumberFormat(undefined, {
            style: 'currency',
            currency: currency || 'USD',
            maximumFractionDigits: 2
        }).format(Number(amount || 0));
    } catch (error) {
        return `${currency || 'USD'} ${Number(amount || 0).toFixed(2)}`;
    }
}

function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value == null ? '' : String(value);
    return div.innerHTML;
}

function escapeAttribute(value) {
    return escapeHtml(value).replace(/"/g, '&quot;');
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
        if (!whatsappNumber) {
            setWhatsappUnlinked();
        }
        return;
    }

    const selectedOption = whatsappNumberSelect.options[whatsappNumberSelect.selectedIndex];
    if (!selectedOption || !selectedOption.value) {
        setWhatsappUnlinked();
        return;
    }

    whatsappNumber = selectedOption.value;
    if (selectedOption.dataset.userId) {
        userId = selectedOption.dataset.userId;
    }

    setWhatsappLinkState('linked');
    setElementText(userIdDisplay, userId);
    setElementText(userWhatsappDisplay, whatsappNumber);
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
                    <input type="text" id="newWhatsappNumber" placeholder="+1XXXXXXXXXX" required>
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
