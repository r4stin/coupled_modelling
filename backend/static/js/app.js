document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const healthBadge = document.getElementById('health-badge');
    const refreshHealthBtn = document.getElementById('refresh-health-btn');
    const classTreeContainer = document.getElementById('class-tree');
    const instancesUl = document.getElementById('instances-ul');
    const selectedClassName = document.getElementById('selected-class-name');
    const instanceSearch = document.getElementById('instance-search');
    const inspectorContent = document.getElementById('inspector-content');

    // State Variables
    let activeClass = null;
    let activeInstance = null;
    let instancesData = []; // Cached summaries list for search filtering
    let classHierarchy = []; // Store hierarchy lists for type mapping on navigation

    // 1. Health Verification Handler
    async function verifyHealth() {
        healthBadge.textContent = 'Verifying...';
        healthBadge.className = 'badge badge-loading';
        try {
            const response = await fetch('/api/v1.0/health/');
            const data = await response.json();
            if (response.ok && data.status === 'ok') {
                healthBadge.textContent = 'CONNECTED';
                healthBadge.className = 'badge badge-connected';
            } else {
                showHealthError(data.error || 'GraphDB repository error');
            }
        } catch (err) {
            showHealthError(err.message || 'API connection failed');
        }
    }

    function showHealthError(msg) {
        healthBadge.textContent = 'OFFLINE';
        healthBadge.className = 'badge badge-error';
        console.error('Health Verification failed:', msg);
    }

    refreshHealthBtn.addEventListener('click', verifyHealth);

    // Dynamic Safe Error Rendering
    function renderContainerError(container, messageText) {
        const p = document.createElement('p');
        p.className = 'status-msg';
        p.style.color = '#f87171';
        p.textContent = `Error: ${messageText}`;
        container.replaceChildren(p);
    }

    function renderContainerMessage(container, messageText) {
        const p = document.createElement('p');
        p.className = 'status-msg';
        p.textContent = messageText;
        container.replaceChildren(p);
    }

    // 2. Class Hierarchy Tree builder
    async function loadClassHierarchy() {
        renderContainerMessage(classTreeContainer, 'Loading class structure...');
        try {
            const response = await fetch('/api/v1.0/get_class_hierarchy_metadata/');
            if (!response.ok) throw new Error('Failed to load class hierarchy metadata');
            classHierarchy = await response.json();
            buildTree(classHierarchy);
        } catch (err) {
            renderContainerError(classTreeContainer, err.message);
            verifyHealth();
        }
    }

    function buildTree(classes) {
        classTreeContainer.innerHTML = '';
        
        const classNames = new Set(classes.map(c => c.class));
        
        // Find roots (nodes with empty parents OR whose parents are not in the list of local classes)
        const roots = classes.filter(c => {
            const localParents = (c.parents || []).filter(p => classNames.has(p));
            return localParents.length === 0;
        });
        
        if (roots.length === 0 && classes.length === 0) {
            renderContainerMessage(classTreeContainer, 'No classes found in the project namespace');
            return;
        }

        const ul = document.createElement('ul');
        ul.className = 'tree-root';
        
        // Global visited set tracks rendered classes across root and cycle rendering trees to avoid isolated duplicate root nodes
        const visited = new Set();
        
        // Render roots
        roots.forEach(root => {
            renderNodeRecursive(root.class, classes, ul, [], visited);
        });
        
        // Handle unrendered cycle loops or orphans
        classes.forEach(item => {
            if (!visited.has(item.class)) {
                renderNodeRecursive(item.class, classes, ul, [], visited);
            }
        });
        
        classTreeContainer.appendChild(ul);
    }

    function renderNodeRecursive(className, classes, parentEl, path, visited) {
        if (path.includes(className)) return; // Current ancestry path cycle guard

        visited.add(className);

        const node = classes.find(c => c.class === className);
        if (!node) return;

        const li = document.createElement('li');
        li.className = 'tree-node';

        const labelContainer = document.createElement('div');
        labelContainer.className = 'tree-node-label-container';
        labelContainer.dataset.class = className;

        // Toggle Expand indicator
        const toggleSpan = document.createElement('span');
        toggleSpan.className = 'tree-toggle-btn';
        
        // Find children (classes that have className as one of their parents)
        const children = classes.filter(c => c.parents && c.parents.includes(className));
        
        if (children.length > 0) {
            toggleSpan.innerHTML = '&#9656;'; // Collapsed chevron
        } else {
            toggleSpan.innerHTML = '&bull;'; // Leaf indicator
        }

        const nameSpan = document.createElement('span');
        nameSpan.className = 'tree-node-name';
        nameSpan.textContent = className;

        labelContainer.appendChild(toggleSpan);
        labelContainer.appendChild(nameSpan);
        li.appendChild(labelContainer);

        // Click selects the class
        labelContainer.addEventListener('click', (e) => {
            e.stopPropagation();
            document.querySelectorAll('.tree-node-label-container').forEach(el => {
                el.classList.remove('selected');
            });
            // Highlight all tree occurrences of this class (multiple inheritance occurrences)
            document.querySelectorAll(`.tree-node-label-container[data-class="${className}"]`).forEach(el => {
                el.classList.add('selected');
            });
            selectClass(className);
        });

        // Toggle children expand/collapse
        if (children.length > 0) {
            const childUl = document.createElement('ul');
            childUl.className = 'tree-children';
            
            toggleSpan.addEventListener('click', (e) => {
                e.stopPropagation();
                const isExpanded = childUl.classList.toggle('expanded');
                toggleSpan.innerHTML = isExpanded ? '&#9662;' : '&#9656;';
            });

            children.forEach(child => {
                renderNodeRecursive(child.class, classes, childUl, [...path, className], visited);
            });
            li.appendChild(childUl);
        }

        parentEl.appendChild(li);
    }

    // 3. Selection Event Handlers
    function selectClass(className) {
        activeClass = className;
        selectedClassName.textContent = className;
        instanceSearch.disabled = false;
        instanceSearch.value = '';
        loadClassInstances(className);
    }

    async function loadClassInstances(className) {
        instancesUl.innerHTML = '';
        const loadingLi = document.createElement('li');
        loadingLi.className = 'status-msg';
        loadingLi.textContent = 'Loading class instances...';
        instancesUl.appendChild(loadingLi);

        try {
            const response = await fetch(`/api/v1.0/get_class_instance_summaries/?class=${encodeURIComponent(className)}`);
            if (!response.ok) throw new Error('Failed to load class instances');
            instancesData = await response.json();
            renderInstancesList(instancesData);
        } catch (err) {
            instancesUl.innerHTML = '';
            const errorLi = document.createElement('li');
            errorLi.className = 'status-msg';
            errorLi.style.color = '#f87171';
            errorLi.textContent = `Error: ${err.message}`;
            instancesUl.appendChild(errorLi);
            verifyHealth();
        }
    }

    function renderInstancesList(items) {
        instancesUl.innerHTML = '';
        if (items.length === 0) {
            const emptyLi = document.createElement('li');
            emptyLi.className = 'status-msg';
            emptyLi.textContent = 'No instances found for this class';
            instancesUl.appendChild(emptyLi);
            return;
        }

        // Group items by their direct subclass type
        const groups = {};
        items.forEach(item => {
            const types = item.types || [];
            if (types.length === 0) {
                const fallbackType = activeClass || 'Unclassified';
                if (!groups[fallbackType]) groups[fallbackType] = [];
                groups[fallbackType].push(item);
            } else {
                types.forEach(t => {
                    if (!groups[t]) groups[t] = [];
                    if (!groups[t].some(x => x.id === item.id)) {
                        groups[t].push(item);
                    }
                });
            }
        });

        // Render each group sequentially
        const sortedTypes = Object.keys(groups).sort();
        sortedTypes.forEach(type => {
            const groupHeader = document.createElement('div');
            groupHeader.className = 'instance-group-header';
            groupHeader.textContent = type;
            instancesUl.appendChild(groupHeader);

            const groupUl = document.createElement('ul');
            groupUl.className = 'instance-group-list';

            groups[type].forEach(item => {
                const li = document.createElement('li');
                li.className = 'instance-item-li';
                li.dataset.id = item.id;
                
                const labelSpan = document.createElement('span');
                labelSpan.className = 'item-primary-label';
                labelSpan.textContent = item.label;
                li.appendChild(labelSpan);

                // If label is different from ID, show ID in parentheses
                if (item.label !== item.id) {
                    const idSpan = document.createElement('span');
                    idSpan.className = 'item-secondary-id';
                    idSpan.textContent = ` (${item.id})`;
                    li.appendChild(idSpan);
                }
                
                if (activeInstance === item.id) {
                    li.classList.add('selected');
                }

                li.addEventListener('click', () => {
                    document.querySelectorAll('#instances-ul li').forEach(el => {
                        el.classList.remove('selected');
                    });
                    document.querySelectorAll(`#instances-ul li[data-id="${item.id}"]`).forEach(el => {
                        el.classList.add('selected');
                    });
                    selectInstance(item.id);
                });

                groupUl.appendChild(li);
            });

            instancesUl.appendChild(groupUl);
        });
    }

    // Filter list via search box
    instanceSearch.addEventListener('input', () => {
        const query = instanceSearch.value.toLowerCase().trim();
        const filtered = instancesData.filter(item => 
            item.label.toLowerCase().includes(query) || 
            item.id.toLowerCase().includes(query) ||
            (item.types || []).some(t => t.toLowerCase().includes(query))
        );
        renderInstancesList(filtered);
    });

    function selectInstance(instId) {
        activeInstance = instId;
        loadInstanceDetails(instId);
    }

    // 4. Instance property metadata loader
    async function loadInstanceDetails(instId) {
        renderContainerMessage(inspectorContent, 'Loading instance property metadata...');
        try {
            const response = await fetch(`/api/v1.0/get_instance_property_metadata/?instance=${encodeURIComponent(instId)}`);
            if (!response.ok) {
                if (response.status === 404) {
                    throw new Error('Selected instance no longer exists in GraphDB.');
                }
                throw new Error('Failed to load instance metadata');
            }
            const data = await response.json();
            renderInspector(data);
        } catch (err) {
            renderContainerError(inspectorContent, err.message);
            verifyHealth();
        }
    }

    function renderInspector(data) {
        inspectorContent.innerHTML = '';

        // Inspector Header Card
        const headerCard = document.createElement('div');
        headerCard.className = 'inspector-detail-header';

        const title = document.createElement('h3');
        title.textContent = data.label;
        headerCard.appendChild(title);

        // Add Unique Instance ID
        const instIdDiv = document.createElement('div');
        instIdDiv.className = 'inspector-instance-id';
        instIdDiv.textContent = `ID: ${data.id}`;
        headerCard.appendChild(instIdDiv);

        const typeContainer = document.createElement('div');
        typeContainer.className = 'inspector-types';
        
        data.types.forEach(type => {
            const tag = document.createElement('span');
            tag.className = 'type-tag';
            tag.textContent = type;
            typeContainer.appendChild(tag);
        });
        headerCard.appendChild(typeContainer);
        inspectorContent.appendChild(headerCard);

        // Properties Grid Table
        if (!data.properties || data.properties.length === 0) {
            const msg = document.createElement('p');
            msg.className = 'status-msg';
            msg.textContent = 'This instance has no properties defined.';
            inspectorContent.appendChild(msg);
            return;
        }

        const table = document.createElement('table');
        table.className = 'metadata-grid-table';

        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        const thProp = document.createElement('th');
        thProp.textContent = 'Property';
        const thVal = document.createElement('th');
        thVal.textContent = 'Values';
        
        headerRow.appendChild(thProp);
        headerRow.appendChild(thVal);
        thead.appendChild(headerRow);
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        data.properties.forEach(prop => {
            const row = document.createElement('tr');
            
            const nameCell = document.createElement('td');
            nameCell.className = 'property-name-cell';
            nameCell.textContent = prop.property;
            
            const valueCell = document.createElement('td');
            const valueList = document.createElement('div');
            valueList.className = 'value-item-list';

            prop.values.forEach(val => {
                const item = document.createElement('div');
                
                if (val.kind === 'object') {
                    // Object Reference Link
                    const link = document.createElement('a');
                    link.className = 'object-link';
                    // Show Label (ID) if they differ, else just ID
                    if (val.label !== val.id) {
                        link.textContent = `${val.label} (${val.id})`;
                    } else {
                        link.textContent = val.id;
                    }
                    link.title = `Navigate to ${val.id}`;
                    link.href = '#';
                    link.addEventListener('click', (e) => {
                        e.preventDefault();
                        navigateToInstance(val.id);
                    });
                    item.appendChild(link);
                } else {
                    // Literal value display
                    const container = document.createElement('div');
                    container.className = 'literal-value-box';
                    
                    const valueSpan = document.createElement('span');
                    valueSpan.className = 'literal-value';
                    valueSpan.textContent = val.value;
                    container.appendChild(valueSpan);

                    if (val.language) {
                        const langSpan = document.createElement('span');
                        langSpan.className = 'literal-lang';
                        langSpan.textContent = val.language;
                        container.appendChild(langSpan);
                    } else if (val.datatype && val.datatype !== 'http://www.w3.org/2001/XMLSchema#string') {
                        const dtSpan = document.createElement('span');
                        dtSpan.className = 'literal-datatype';
                        dtSpan.textContent = val.datatype.split('#')[1] || val.datatype;
                        container.appendChild(dtSpan);
                    }
                    
                    item.appendChild(container);
                }
                valueList.appendChild(item);
            });
            
            valueCell.appendChild(valueList);
            row.appendChild(nameCell);
            row.appendChild(valueCell);
            tbody.appendChild(row);
        });

        table.appendChild(tbody);
        inspectorContent.appendChild(table);
    }

    // 5. Linked Object Navigation
    async function navigateToInstance(instId) {
        try {
            const response = await fetch(`/api/v1.0/get_instance_property_metadata/?instance=${encodeURIComponent(instId)}`);
            if (!response.ok) throw new Error('Target resource not found');
            const data = await response.json();
            
            const targetClass = data.types[0];
            if (targetClass) {
                const nodeEl = document.querySelector(`.tree-node-label-container[data-class="${targetClass}"]`);
                if (nodeEl) {
                    // Expand parents in tree
                    let parentUl = nodeEl.parentElement.parentElement;
                    while (parentUl && parentUl.classList.contains('tree-children')) {
                        parentUl.classList.add('expanded');
                        const expandBtn = parentUl.parentElement.querySelector('.tree-toggle-btn');
                        if (expandBtn && expandBtn.innerHTML === '▸') {
                            expandBtn.innerHTML = '▾';
                        }
                        parentUl = parentUl.parentElement.parentElement;
                    }
                    
                    document.querySelectorAll('.tree-node-label-container').forEach(el => {
                        el.classList.remove('selected');
                    });
                    document.querySelectorAll(`.tree-node-label-container[data-class="${targetClass}"]`).forEach(el => {
                        el.classList.add('selected');
                    });
                    
                    activeClass = targetClass;
                    selectedClassName.textContent = targetClass;
                    instanceSearch.disabled = false;
                    instanceSearch.value = '';
                }
            }
            
            activeInstance = instId;
            if (activeClass) {
                const summariesResponse = await fetch(`/api/v1.0/get_class_instance_summaries/?class=${encodeURIComponent(activeClass)}`);
                if (summariesResponse.ok) {
                    instancesData = await summariesResponse.json();
                    renderInstancesList(instancesData);
                }
            }
            
            renderInspector(data);
        } catch (err) {
            alert(`Could not navigate to target resource: ${err.message}`);
            verifyHealth();
        }
    }

    // Initialize Page
    verifyHealth();
    loadClassHierarchy();
});
