document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const healthBadge = document.getElementById('health-badge');
    const refreshHealthBtn = document.getElementById('refresh-health-btn');
    const classTreeContainer = document.getElementById('class-tree');
    const instancesUl = document.getElementById('instances-ul');
    const selectedClassName = document.getElementById('selected-class-name');
    const instanceSearch = document.getElementById('instance-search');
    const inspectorContent = document.getElementById('inspector-content');

    // Interactive UI Elements
    const importBtn = document.getElementById('import-btn');
    const downloadOwlBtn = document.getElementById('download-owl-btn');
    const importFileInput = document.getElementById('import-file-input');
    const importModal = document.getElementById('import-modal');
    const importLabelInput = document.getElementById('import-label-input');
    const importCancelBtn = document.getElementById('import-cancel-btn');
    const importConfirmBtn = document.getElementById('import-confirm-btn');

    const addClassInstanceBtn = document.getElementById('add-class-instance-btn');
    const createInstanceModal = document.getElementById('create-instance-modal');
    const createClassLabelTarget = document.getElementById('create-class-label-target');
    const createInstanceLabelInput = document.getElementById('create-instance-label-input');
    const createInstanceCancelBtn = document.getElementById('create-instance-cancel-btn');
    const createInstanceConfirmBtn = document.getElementById('create-instance-confirm-btn');

    const exportKratosBtn = document.getElementById('export-kratos-btn');
    const deleteInstanceBtn = document.getElementById('delete-instance-btn');
    const addChildPropertyBtn = document.getElementById('add-child-property-btn');
    const addChildModal = document.getElementById('add-child-modal');
    const childPropertySelect = document.getElementById('child-property-select');
    const childLabelInput = document.getElementById('child-label-input');
    const addChildCancelBtn = document.getElementById('add-child-cancel-btn');
    const addChildConfirmBtn = document.getElementById('add-child-confirm-btn');
    const globalSearchInput = document.getElementById('global-search-input');
    const globalSearchResults = document.getElementById('global-search-results');

    // Utility: HTML Escaping
    function escapeHtml(str) {
        if (str === null || str === undefined) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    // Toast Notification Component
    function showToast(message, type = 'info', duration = 3000) {
        const container = document.getElementById('toast-container');
        if (!container) return;
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        const iconMap = {
            success: '✓',
            error: '✕',
            warning: '⚠',
            info: 'ℹ'
        };
        toast.innerHTML = `
            <span class="toast-icon">${iconMap[type] || 'ℹ'}</span>
            <span class="toast-message">${escapeHtml(message)}</span>
        `;
        container.appendChild(toast);
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, duration);
    }

    // State Variables
    let activeClass = null;
    let activeInstance = null;
    let instancesData = []; // Cached summaries list for search filtering
    let classHierarchy = []; // Store hierarchy lists for type mapping on navigation
    let allInstancesCache = null; // Cache for global search
    const classParentMap = {};

    // Cache parents hierarchy map for subclass checks
    function cacheParentMap(classes) {
        classes.forEach(c => {
            classParentMap[c.class] = c.parents || [];
        });
    }

    function isSubclassOf(className, targetParent) {
        if (className === targetParent) return true;
        const parents = classParentMap[className] || [];
        for (const p of parents) {
            if (isSubclassOf(p, targetParent)) return true;
        }
        return false;
    }

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

    refreshHealthBtn.addEventListener('click', async () => {
        await verifyHealth();
        if (healthBadge.classList.contains('badge-connected')) {
            loadClassHierarchy();
        }
    });

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
            cacheParentMap(classHierarchy);
            buildTree(classHierarchy);
        } catch (err) {
            renderContainerError(classTreeContainer, err.message);
            verifyHealth();
        }
    }

    function buildTree(classes) {
        classTreeContainer.innerHTML = '';
        const classNames = new Set(classes.map(c => c.class));
        
        // Find roots
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
        
        const visited = new Set();
        
        roots.forEach(root => {
            renderNodeRecursive(root.class, classes, ul, [], visited);
        });
        
        classes.forEach(item => {
            if (!visited.has(item.class)) {
                renderNodeRecursive(item.class, classes, ul, [], visited);
            }
        });
        
        classTreeContainer.appendChild(ul);
    }

    function renderNodeRecursive(className, classes, parentEl, path, visited) {
        if (path.includes(className)) return; // Cycle guard

        visited.add(className);

        const node = classes.find(c => c.class === className);
        if (!node) return;

        const li = document.createElement('li');
        li.className = 'tree-node';

        const labelContainer = document.createElement('div');
        labelContainer.className = 'tree-node-label-container';
        labelContainer.dataset.class = className;

        const toggleSpan = document.createElement('span');
        toggleSpan.className = 'tree-toggle-btn';
        
        const children = classes.filter(c => c.parents && c.parents.includes(className));
        
        if (children.length > 0) {
            toggleSpan.innerHTML = '&#9656;'; // Collapsed chevron
        } else {
            toggleSpan.innerHTML = '&bull;'; // Leaf
        }

        const nameSpan = document.createElement('span');
        nameSpan.className = 'tree-node-name';
        nameSpan.textContent = className;

        labelContainer.appendChild(toggleSpan);
        labelContainer.appendChild(nameSpan);
        li.appendChild(labelContainer);

        labelContainer.addEventListener('click', (e) => {
            e.stopPropagation();
            document.querySelectorAll('.tree-node-label-container').forEach(el => {
                el.classList.remove('selected');
            });
            document.querySelectorAll(`.tree-node-label-container[data-class="${className}"]`).forEach(el => {
                el.classList.add('selected');
            });
            selectClass(className);
        });

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
    const classMetadataContainer = document.getElementById('class-metadata-container');

    function selectClass(className) {
        activeClass = className;
        selectedClassName.textContent = className;
        instanceSearch.disabled = false;
        instanceSearch.value = '';
        addClassInstanceBtn.disabled = false;
        loadClassData(className);
    }

    async function loadClassData(className) {
        instancesUl.innerHTML = '';
        const loadingLi = document.createElement('li');
        loadingLi.className = 'status-msg';
        loadingLi.textContent = 'Loading class instances...';
        instancesUl.appendChild(loadingLi);

        classMetadataContainer.style.display = 'none';
        classMetadataContainer.innerHTML = '';

        // Fetch class metadata and instances concurrently
        const metadataPromise = fetch(`/api/v1.0/get_class_metadata/?class=${encodeURIComponent(className)}`)
            .then(async res => {
                if (!res.ok) throw new Error('Failed to load class metadata');
                return res.json();
            })
            .then(data => {
                renderClassMetadata(data);
            })
            .catch(err => {
                renderClassMetadataError(err.message);
            });

        const instancesPromise = fetch(`/api/v1.0/get_class_instance_summaries/?class=${encodeURIComponent(className)}`)
            .then(async res => {
                if (!res.ok) throw new Error('Failed to load class instances');
                return res.json();
            })
            .then(data => {
                instancesData = data;
                renderInstancesList(instancesData);
            })
            .catch(err => {
                instancesUl.innerHTML = '';
                const errorLi = document.createElement('li');
                errorLi.className = 'status-msg';
                errorLi.style.color = '#f87171';
                errorLi.textContent = `Error: ${err.message}`;
                instancesUl.appendChild(errorLi);
                verifyHealth();
            });

        await Promise.allSettled([metadataPromise, instancesPromise]);
    }

    function renderClassMetadata(data) {
        classMetadataContainer.innerHTML = '';
        classMetadataContainer.style.display = 'block';

        // 1. Descriptions
        if (data.descriptions && data.descriptions.length > 0) {
            data.descriptions.forEach(desc => {
                const descP = document.createElement('p');
                descP.className = 'class-description';
                descP.textContent = desc;
                classMetadataContainer.appendChild(descP);
            });
        } else {
            const descP = document.createElement('p');
            descP.className = 'class-description muted-msg';
            descP.textContent = 'No description available';
            classMetadataContainer.appendChild(descP);
        }

        // 2. Parents and Children / Subclasses
        const relationshipsDiv = document.createElement('div');
        relationshipsDiv.className = 'class-relationships';

        // Superclasses
        const superDiv = document.createElement('div');
        superDiv.className = 'relationship-group';
        superDiv.innerHTML = '<span class="relationship-label">Superclasses: </span>';
        if (data.superclasses && data.superclasses.length > 0) {
            data.superclasses.forEach((s, idx) => {
                const link = document.createElement('span');
                link.className = 'class-nav-link';
                link.textContent = s.label;
                link.addEventListener('click', () => {
                    selectClassInTreeAndLoad(s.id);
                });
                superDiv.appendChild(link);
                if (idx < data.superclasses.length - 1) {
                    superDiv.appendChild(document.createTextNode(', '));
                }
            });
        } else {
            const span = document.createElement('span');
            span.className = 'muted-msg';
            span.textContent = 'None (Root Class)';
            superDiv.appendChild(span);
        }
        relationshipsDiv.appendChild(superDiv);

        // Subclasses
        const subDiv = document.createElement('div');
        subDiv.className = 'relationship-group';
        subDiv.innerHTML = '<span class="relationship-label">Subclasses: </span>';
        if (data.subclasses && data.subclasses.length > 0) {
            data.subclasses.forEach((s, idx) => {
                const link = document.createElement('span');
                link.className = 'class-nav-link';
                link.textContent = s.label;
                link.addEventListener('click', () => {
                    selectClassInTreeAndLoad(s.id);
                });
                subDiv.appendChild(link);
                if (idx < data.subclasses.length - 1) {
                    subDiv.appendChild(document.createTextNode(', '));
                }
            });
        } else {
            const span = document.createElement('span');
            span.className = 'muted-msg';
            span.textContent = 'None (Leaf Class)';
            subDiv.appendChild(span);
        }
        relationshipsDiv.appendChild(subDiv);

        // Equivalent classes
        const eqDiv = document.createElement('div');
        eqDiv.className = 'relationship-group';
        eqDiv.innerHTML = '<span class="relationship-label">Equivalent to: </span>';
        if (data.equivalent_classes && data.equivalent_classes.length > 0) {
            data.equivalent_classes.forEach((e, idx) => {
                const link = document.createElement('span');
                link.className = 'class-nav-link';
                link.textContent = e.label;
                link.addEventListener('click', () => {
                    selectClassInTreeAndLoad(e.id);
                });
                eqDiv.appendChild(link);
                if (idx < data.equivalent_classes.length - 1) {
                    eqDiv.appendChild(document.createTextNode(', '));
                }
            });
        } else {
            const span = document.createElement('span');
            span.className = 'muted-msg';
            span.textContent = 'None';
            eqDiv.appendChild(span);
        }
        relationshipsDiv.appendChild(eqDiv);
        
        classMetadataContainer.appendChild(relationshipsDiv);

        // 3. Asserted Restrictions
        const axiomsDiv = document.createElement('div');
        axiomsDiv.className = 'class-axioms';
        axiomsDiv.innerHTML = '<div class="axioms-label">Asserted Restrictions:</div>';

        if (data.restrictions && data.restrictions.length > 0) {
            const list = document.createElement('ul');
            list.className = 'axioms-list';
            data.restrictions.forEach(r => {
                const li = document.createElement('li');
                li.className = 'axiom-item';

                // 1. Property Name
                const propSpan = document.createElement('span');
                propSpan.className = 'axiom-prop';
                propSpan.textContent = r.property.label;
                li.appendChild(propSpan);
                li.appendChild(document.createTextNode(' '));
                
                // 2. Quantifier kind
                let kindText = r.kind;
                if (r.kind === 'some_values_from') kindText = 'some';
                else if (r.kind === 'all_values_from') kindText = 'all';
                else if (r.kind === 'has_value') kindText = 'value';
                else if (r.kind === 'qualified_cardinality') kindText = 'exactly';
                else if (r.kind === 'min_qualified_cardinality') kindText = 'min';
                else if (r.kind === 'max_qualified_cardinality') kindText = 'max';
                else if (r.kind === 'cardinality') kindText = 'exactly';
                else if (r.kind === 'min_cardinality') kindText = 'min';
                else if (r.kind === 'max_cardinality') kindText = 'max';

                const kindSpan = document.createElement('span');
                kindSpan.className = 'axiom-kind';
                kindSpan.textContent = kindText;
                li.appendChild(kindSpan);
                li.appendChild(document.createTextNode(' '));
                
                // 3. Optional Cardinality Value
                if (r.cardinality !== undefined) {
                    const cardinalitySpan = document.createElement('span');
                    cardinalitySpan.className = 'axiom-cardinality';
                    cardinalitySpan.textContent = r.cardinality;
                    li.appendChild(cardinalitySpan);
                    li.appendChild(document.createTextNode(' '));
                }

                // 4. Target class/bnode/intersection/literal
                if (r.target) {
                    const targetWrapper = document.createElement('span');
                    if (r.target_kind === 'class') {
                        const link = document.createElement('span');
                        link.className = 'axiom-target class-nav-link';
                        link.dataset.targetId = r.target.id;
                        link.textContent = r.target.label;
                        link.addEventListener('click', () => {
                            selectClassInTreeAndLoad(r.target.id);
                        });
                        targetWrapper.appendChild(link);
                    } else if (r.target_kind === 'intersection') {
                        r.target.members.forEach((m, idx) => {
                            const link = document.createElement('span');
                            link.className = 'axiom-target class-nav-link';
                            link.dataset.targetId = m.id;
                            link.textContent = m.label;
                            link.addEventListener('click', () => {
                                selectClassInTreeAndLoad(m.id);
                            });
                            targetWrapper.appendChild(link);
                            
                            if (idx < r.target.members.length - 1) {
                                targetWrapper.appendChild(document.createTextNode(' & '));
                            }
                        });
                    } else {
                        const nonNavLink = document.createElement('span');
                        nonNavLink.className = 'axiom-target-non-nav';
                        nonNavLink.textContent = r.target.label;
                        targetWrapper.appendChild(nonNavLink);
                    }
                    li.appendChild(targetWrapper);
                }

                list.appendChild(li);
            });
            axiomsDiv.appendChild(list);
        } else {
            const span = document.createElement('span');
            span.className = 'muted-msg';
            span.textContent = 'No class restrictions asserted';
            axiomsDiv.appendChild(span);
        }
        classMetadataContainer.appendChild(axiomsDiv);
    }

    function renderClassMetadataError(msg) {
        classMetadataContainer.innerHTML = '';
        classMetadataContainer.style.display = 'block';
        const p = document.createElement('p');
        p.className = 'status-msg';
        p.style.color = '#f87171';
        p.textContent = `Warning: ${msg}`;
        classMetadataContainer.appendChild(p);
    }

    function selectClassInTreeAndLoad(className) {
        const label = document.querySelector(`.tree-node-label-container[data-class="${className}"]`);
        if (label) {
            let parentNode = label.closest('.tree-children');
            while (parentNode) {
                parentNode.classList.add('expanded');
                const parentLi = parentNode.closest('.tree-node');
                if (parentLi) {
                    const toggle = parentLi.querySelector(':scope > .tree-node-label-container > .tree-toggle-btn');
                    if (toggle && (toggle.innerHTML === '▸' || toggle.innerHTML === '&#9656;')) {
                        toggle.innerHTML = '&#9662;'; // expanded chevron ▾
                    }
                }
                parentNode = parentNode.parentElement.closest('.tree-children');
            }
            
            document.querySelectorAll('.tree-node-label-container').forEach(el => {
                el.classList.remove('selected');
            });
            document.querySelectorAll(`.tree-node-label-container[data-class="${className}"]`).forEach(el => {
                el.classList.add('selected');
            });
            
            label.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        }
        selectClass(className);
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

                if (item.label !== item.id) {
                    const idSpan = document.createElement('span');
                    idSpan.className = 'item-secondary-id';
                    idSpan.textContent = ` (${item.id})`;
                    li.appendChild(idSpan);
                }

                if (item.property_preview && item.property_preview.length > 0) {
                    const previewDiv = document.createElement('div');
                    previewDiv.className = 'instance-preview-container';
                    
                    item.property_preview.forEach((p, idx) => {
                        const chip = document.createElement('span');
                        chip.className = 'preview-chip';
                        
                        let valStr = p.value;
                        if (typeof p.value === 'boolean') {
                            valStr = p.value ? 'true' : 'false';
                        }
                        
                        chip.innerHTML = `<span class="preview-key">${escapeHtml(p.property)}:</span> <span class="preview-val">${escapeHtml(valStr)}</span>`;
                        previewDiv.appendChild(chip);
                        
                        if (idx < item.property_preview.length - 1) {
                            const separator = document.createElement('span');
                            separator.className = 'preview-separator';
                            separator.innerHTML = ' &middot; ';
                            previewDiv.appendChild(separator);
                        }
                    });
                    
                    if (item.preview_truncated) {
                        const trunc = document.createElement('span');
                        trunc.className = 'preview-trunc';
                        trunc.innerHTML = ' &middot; <span class="preview-more">+ more</span>';
                        previewDiv.appendChild(trunc);
                    }
                    
                    li.appendChild(previewDiv);
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

    // 4. Detailed Inspector Rendering
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
            deleteInstanceBtn.style.display = 'none';
            exportKratosBtn.style.display = 'none';
            addChildPropertyBtn.style.display = 'none';
            renderContainerError(inspectorContent, err.message);
            verifyHealth();
        }
    }

    function renderInspector(data) {
        inspectorContent.innerHTML = '';

        // Header section
        const headerCard = document.createElement('div');
        headerCard.className = 'inspector-detail-header';

        const title = document.createElement('h3');
        title.textContent = data.label;
        headerCard.appendChild(title);

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

        // Check if coupled_system or subclass to show/hide JSON export
        const isCoupledSystem = data.types.some(t => isSubclassOf(t, "coupled_system"));
        if (isCoupledSystem) {
            exportKratosBtn.style.display = 'inline-block';
        } else {
            exportKratosBtn.style.display = 'none';
        }
        deleteInstanceBtn.style.display = 'inline-block';
        addChildPropertyBtn.style.display = 'inline-block';

        // Prepare select options for Linked Child Creation
        const propertiesList = [
            { prop: "solver_settings", label: "solver_settings (Solver settings)" },
            { prop: "coupling_sequence", label: "coupling_sequence (Coupling loop list)" },
            { prop: "solvers", label: "solvers (Co-simulation solvers)" },
            { prop: "data_transfer_operators", label: "data_transfer_operators (Mesh mappers)" },
            { prop: "input_data_list", label: "input_data_list (Input configuration fields)" },
            { prop: "output_data_list", label: "output_data_list (Output configuration fields)" },
            { prop: "data", label: "data (Input/output variables)" },
            { prop: "convergence_accelerators", label: "convergence_accelerators (Accelerators)" },
            { prop: "convergence_criteria", label: "convergence_criteria (Criteria)" },
            { prop: "mapper_settings", label: "mapper_settings (Mapper settings)" },
            { prop: "io_settings", label: "io_settings (I/O settings)" },
            { prop: "solver_wrapper_settings", label: "solver_wrapper_settings (Wrapper settings)" }
        ];
        childPropertySelect.innerHTML = '';
        propertiesList.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.prop;
            opt.textContent = p.label;
            childPropertySelect.appendChild(opt);
        });

        if (!data.properties || data.properties.length === 0) {
            const msg = document.createElement('p');
            msg.className = 'status-msg';
            msg.textContent = 'This instance has no properties defined.';
            inspectorContent.appendChild(msg);
            renderAddValueControls(data);
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
                item.className = 'prop-value-row';
                
                if (val.kind === 'object') {
                    const link = document.createElement('a');
                    link.className = 'object-link';
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

                    // Add edit listener on literal double-click
                    item.addEventListener('dblclick', (e) => {
                        e.stopPropagation();
                        startInlineEdit(item, val, prop.property, data.id);
                    });
                }

                // Add delete trash button
                const trashBtn = document.createElement('button');
                trashBtn.className = 'trash-btn';
                trashBtn.innerHTML = '&#128465;';
                trashBtn.title = 'Delete specific value';
                trashBtn.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    if (!confirm(`Are you sure you want to delete this value?`)) return;
                    
                    let valPayload = null;
                    if (val.kind === 'object') {
                        valPayload = { kind: 'object', id: val.id };
                    } else {
                        valPayload = { 
                            kind: 'literal', 
                            value: val.value, 
                            datatype: val.datatype || 'http://www.w3.org/2001/XMLSchema#string' 
                        };
                    }
                    
                    try {
                        const response = await fetch('/api/v1.0/delete_value/', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                instance: data.id,
                                property: prop.property,
                                value: valPayload
                            })
                        });
                        
                        if (!response.ok) {
                            const resJson = await response.json();
                            throw new Error(resJson.error || 'Delete failed');
                        }
                        
                        loadInstanceDetails(data.id);
                    } catch (err) {
                        showToast(`Delete failed: ${err.message}`, 'error');
                    }
                });
                item.appendChild(trashBtn);
                valueList.appendChild(item);
            });
            
            valueCell.appendChild(valueList);
            row.appendChild(nameCell);
            row.appendChild(valueCell);
            tbody.appendChild(row);
        });

        table.appendChild(tbody);
        inspectorContent.appendChild(table);

        // Add literal append controls at the bottom of the table
        renderAddValueControls(data);
    }

    function renderAddValueControls(data) {
        const addValRow = document.createElement('div');
        addValRow.className = 'add-value-row';
        
        const propSelect = document.createElement('select');
        const commonProperties = [
            { prop: "label", label: "label (Label)" },
            { prop: "name", label: "name (Name)" },
            { prop: "echo_level", label: "echo_level" },
            { prop: "start_time", label: "start_time" },
            { prop: "end_time", label: "end_time" },
            { prop: "dimension", label: "dimension" },
            { prop: "parallel_type", label: "parallel_type" },
            { prop: "print_colors", label: "print_colors" },
            { prop: "use_initial_configuration", label: "use_initial_configuration" },
            { prop: "abs_tolerance", label: "abs_tolerance" },
            { prop: "rel_tolerance", label: "rel_tolerance" },
            { prop: "variable_name", label: "variable_name" },
            { prop: "location", label: "location" },
            { prop: "mapper_type", label: "mapper_type" },
            { prop: "type", label: "type (Class Type)" },
            { prop: "solver", label: "solver (link to Solver ID)" },
            { prop: "connect_to", label: "connect_to (link to Solver ID)" },
            { prop: "from_solver", label: "from_solver (link to Solver ID)" },
            { prop: "to_solver", label: "to_solver (link to Solver ID)" },
            { prop: "data_transfer_operator", label: "data_transfer_operator (link)" },
            { prop: "mapper_settings", label: "mapper_settings (link)" },
            { prop: "io_settings", label: "io_settings (link)" }
        ];
        commonProperties.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.prop;
            opt.textContent = p.label;
            propSelect.appendChild(opt);
        });
        
        const typeSelect = document.createElement('select');
        const types = [
            { val: "string", text: "String" },
            { val: "integer", text: "Integer" },
            { val: "double", text: "Double" },
            { val: "boolean", text: "Boolean" },
            { val: "object", text: "Object ID" }
        ];
        types.forEach(t => {
            const opt = document.createElement('option');
            opt.value = t.val;
            opt.textContent = t.text;
            typeSelect.appendChild(opt);
        });
        
        const inputVal = document.createElement('input');
        inputVal.type = 'text';
        inputVal.placeholder = 'Enter value or instance ID...';
        
        const btnAddVal = document.createElement('button');
        btnAddVal.className = 'btn-add';
        btnAddVal.textContent = 'Add';
        
        addValRow.appendChild(propSelect);
        addValRow.appendChild(typeSelect);
        addValRow.appendChild(inputVal);
        addValRow.appendChild(btnAddVal);
        inspectorContent.appendChild(addValRow);
        
        btnAddVal.addEventListener('click', async () => {
            const propName = propSelect.value;
            const valType = typeSelect.value;
            const rawVal = inputVal.value.trim();
            
            if (rawVal === '') {
                showToast('Please enter a value', 'warning');
                return;
            }
            
            let finalVal = rawVal;
            if (valType === 'integer') {
                finalVal = parseInt(rawVal, 10);
                if (isNaN(finalVal)) {
                    showToast('Value must be a valid integer', 'warning');
                    return;
                }
            } else if (valType === 'double') {
                finalVal = parseFloat(rawVal);
                if (isNaN(finalVal)) {
                    showToast('Value must be a valid double', 'warning');
                    return;
                }
            } else if (valType === 'boolean') {
                finalVal = rawVal.toLowerCase() in { 'true': 1, 'yes': 1, '1': 1 };
            } else if (valType === 'object') {
                if (!rawVal.startsWith('instance')) {
                    showToast('Linked Object ID must start with "instance" prefix (e.g. instance_24)', 'warning');
                    return;
                }
            }
            
            try {
                btnAddVal.disabled = true;
                btnAddVal.textContent = '...';
                
                const response = await fetch('/api/v1.0/add_values/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        instance: data.id,
                        data: {
                            [propName]: finalVal
                        }
                    })
                });
                
                const resJson = await response.json();
                if (!response.ok) {
                    throw new Error(resJson.error || 'Add value failed');
                }
                
                loadInstanceDetails(data.id);
            } catch (err) {
                showToast(`Add value failed: ${err.message}`, 'error');
            } finally {
                btnAddVal.disabled = false;
                btnAddVal.textContent = 'Add';
            }
        });
    }

    function startInlineEdit(container, val, propName, instId) {
        container.innerHTML = '';
        
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'edit-input-field';
        input.value = val.value;
        
        const actions = document.createElement('div');
        actions.className = 'edit-actions-container';
        
        const saveBtn = document.createElement('button');
        saveBtn.className = 'btn-inline-save';
        saveBtn.textContent = 'Save';
        
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'btn-inline-cancel';
        cancelBtn.textContent = 'X';
        
        actions.appendChild(saveBtn);
        actions.appendChild(cancelBtn);
        container.appendChild(input);
        container.appendChild(actions);
        
        input.focus();
        
        cancelBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            loadInstanceDetails(instId);
        });
        
        saveBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const newValue = input.value.trim();
            if (newValue === '') {
                showToast('Value cannot be empty', 'warning');
                return;
            }
            
            let addValue = newValue;
            if (val.datatype === 'http://www.w3.org/2001/XMLSchema#integer') {
                addValue = parseInt(newValue, 10);
                if (isNaN(addValue)) {
                    showToast('Value must be a valid integer', 'warning');
                    return;
                }
            } else if (val.datatype === 'http://www.w3.org/2001/XMLSchema#double' || val.datatype === 'http://www.w3.org/2001/XMLSchema#decimal') {
                addValue = parseFloat(newValue);
                if (isNaN(addValue)) {
                    showToast('Value must be a valid double', 'warning');
                    return;
                }
            } else if (val.datatype === 'http://www.w3.org/2001/XMLSchema#boolean') {
                addValue = newValue.toLowerCase() in { 'true': 1, 'yes': 1, '1': 1 };
            }
            
            try {
                saveBtn.disabled = true;
                saveBtn.textContent = '...';
                
                // 1. Delete old value (exact match format)
                const delRes = await fetch('/api/v1.0/delete_value/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        instance: instId,
                        property: propName,
                        value: {
                            kind: 'literal',
                            value: val.value,
                            datatype: val.datatype || 'http://www.w3.org/2001/XMLSchema#string'
                        }
                    })
                });
                
                if (!delRes.ok) {
                    const resJson = await delRes.json();
                    throw new Error(resJson.error || 'Failed to remove old value');
                }
                
                // 2. Add new value (primitive python format)
                const addRes = await fetch('/api/v1.0/add_values/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        instance: instId,
                        data: {
                            [propName]: addValue
                        }
                    })
                });
                
                if (!addRes.ok) {
                    const resJson = await addRes.json();
                    throw new Error(resJson.error || 'Failed to write new value');
                }
                
                loadInstanceDetails(instId);
            } catch (err) {
                showToast(`Edit failed: ${err.message}`, 'error');
                loadInstanceDetails(instId);
            }
        });
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
                    let parentUl = nodeEl.parentElement.parentElement;
                    while (parentUl && parentUl.classList.contains('tree-children')) {
                        parentUl.classList.add('expanded');
                        const expandBtn = parentUl.parentElement.querySelector('.tree-toggle-btn');
                        if (expandBtn && expandBtn.innerHTML === '&#9656;') {
                            expandBtn.innerHTML = '&#9662;';
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
            showToast(`Could not navigate to target resource: ${err.message}`, 'error');
            verifyHealth();
        }
    }

    // Event Handlers for Upload/Download/Instance Creation
    importBtn.addEventListener('click', () => {
        importFileInput.click();
    });

    importFileInput.addEventListener('change', () => {
        const file = importFileInput.files[0];
        if (!file) return;
        
        let baseName = file.name;
        if (baseName.endsWith('.json')) {
            baseName = baseName.substring(0, baseName.length - 5);
        }
        importLabelInput.value = baseName.replace(/[_-]/g, ' ');
        importModal.style.display = 'flex';
    });

    importCancelBtn.addEventListener('click', () => {
        importModal.style.display = 'none';
        importFileInput.value = '';
    });

    importConfirmBtn.addEventListener('click', () => {
        const file = importFileInput.files[0];
        if (!file) return;
        
        const reader = new FileReader();
        reader.onload = async (e) => {
            try {
                const content = e.target.result;
                const jsonData = JSON.parse(content);
                
                const labelVal = importLabelInput.value.trim();
                if (!labelVal) {
                    showToast('Please enter a configuration label', 'warning');
                    return;
                }
                
                importConfirmBtn.disabled = true;
                importConfirmBtn.textContent = 'Importing...';
                
                const response = await fetch('/api/v1.0/import_coupled_kratos/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        data: jsonData,
                        label: labelVal
                    })
                });
                
                const resData = await response.json();
                if (!response.ok) {
                    throw new Error(resData.error || 'Import failed');
                }
                
                allInstancesCache = null; // Invalidate global search cache
                showToast('Configuration imported successfully!', 'success');
                importModal.style.display = 'none';
                importFileInput.value = '';
                
                await loadClassHierarchy();
                selectClass('coupled_system');
                setTimeout(() => {
                    const newInstItem = document.querySelector(`.instance-item-li[data-id="${resData}"]`);
                    if (newInstItem) {
                        newInstItem.click();
                    } else {
                        selectInstance(resData);
                    }
                }, 500);
            } catch (err) {
                showToast(`Import failed: ${err.message}`, 'error');
            } finally {
                importConfirmBtn.disabled = false;
                importConfirmBtn.textContent = 'Import';
            }
        };
        reader.readAsText(file);
    });

    downloadOwlBtn.addEventListener('click', () => {
        window.location.href = '/api/v1.0/download_owl/';
    });

    exportKratosBtn.addEventListener('click', async () => {
        if (!activeInstance) return;
        try {
            exportKratosBtn.disabled = true;
            exportKratosBtn.textContent = 'Exporting...';
            
            const response = await fetch('/api/v1.0/export_coupled_kratos/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ coupled_system: activeInstance })
            });
            
            if (!response.ok) {
                const resData = await response.json();
                throw new Error(resData.error || 'Export failed');
            }
            
            const exportData = await response.json();
            const blob = new Blob([JSON.stringify(exportData, null, 4)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${activeInstance}_kratos.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (err) {
            showToast(`Export failed: ${err.message}`, 'error');
        } finally {
            exportKratosBtn.disabled = false;
            exportKratosBtn.textContent = 'Export JSON';
        }
    });

    if (deleteInstanceBtn) {
        deleteInstanceBtn.addEventListener('click', async () => {
            if (!activeInstance) return;

            const instLabel = activeInstance;
            const confirmed = confirm(`Are you sure you want to permanently delete instance "${instLabel}" from GraphDB?`);
            if (!confirmed) return;

            try {
                deleteInstanceBtn.disabled = true;
                deleteInstanceBtn.textContent = 'Deleting...';

                const response = await fetch('/api/v1.0/delete_instance/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ instance: activeInstance })
                });

                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.error || 'Failed to delete instance');
                }

                allInstancesCache = null;
                showToast(`Instance "${instLabel}" deleted successfully from GraphDB`, 'success');
                
                activeInstance = null;
                deleteInstanceBtn.style.display = 'none';
                exportKratosBtn.style.display = 'none';
                addChildPropertyBtn.style.display = 'none';
                
                inspectorContent.innerHTML = '<div class="empty-state"><p>Select an instance from the list to view its properties.</p></div>';

                if (activeClass) {
                    await loadClassData(activeClass);
                }
            } catch (err) {
                console.error('Delete instance error:', err);
                showToast(`Delete instance failed: ${err.message}`, 'error');
            } finally {
                deleteInstanceBtn.disabled = false;
                deleteInstanceBtn.textContent = 'Delete Instance';
            }
        });
    }

    addClassInstanceBtn.addEventListener('click', () => {
        if (!activeClass) return;
        createClassLabelTarget.textContent = activeClass;
        createInstanceLabelInput.value = '';
        createInstanceModal.style.display = 'flex';
    });

    createInstanceCancelBtn.addEventListener('click', () => {
        createInstanceModal.style.display = 'none';
    });

    createInstanceConfirmBtn.addEventListener('click', async () => {
        const labelVal = createInstanceLabelInput.value.trim();
        if (!labelVal) {
            showToast('Please enter a label for the new instance', 'warning');
            return;
        }
        
        try {
            createInstanceConfirmBtn.disabled = true;
            createInstanceConfirmBtn.textContent = 'Creating...';
            
            const response = await fetch('/api/v1.0/create_class_instance/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    class: activeClass,
                    label: labelVal
                })
            });
            
            const resData = await response.json();
            if (!response.ok) {
                throw new Error(resData.error || 'Creation failed');
            }
            
            allInstancesCache = null; // Invalidate global search cache
            showToast('Instance created successfully!', 'success');
            createInstanceModal.style.display = 'none';
            
            await loadClassData(activeClass);
            setTimeout(() => {
                const item = document.querySelector(`.instance-item-li[data-id="${resData}"]`);
                if (item) item.click();
            }, 300);
        } catch (err) {
            showToast(`Creation failed: ${err.message}`, 'error');
        } finally {
            createInstanceConfirmBtn.disabled = false;
            createInstanceConfirmBtn.textContent = 'Create';
        }
    });

    addChildPropertyBtn.addEventListener('click', () => {
        if (!activeInstance) return;
        childLabelInput.value = '';
        addChildModal.style.display = 'flex';
    });

    addChildCancelBtn.addEventListener('click', () => {
        addChildModal.style.display = 'none';
    });

    addChildConfirmBtn.addEventListener('click', async () => {
        const propVal = childPropertySelect.value;
        const labelVal = childLabelInput.value.trim();
        
        if (!labelVal) {
            showToast('Please enter a label for the child instance', 'warning');
            return;
        }
        
        try {
            addChildConfirmBtn.disabled = true;
            addChildConfirmBtn.textContent = 'Adding...';
            
            const response = await fetch('/api/v1.0/create_instance/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    property: propVal,
                    parent: activeInstance,
                    data: {
                        label: labelVal
                    }
                })
            });
            
            const resData = await response.json();
            if (!response.ok) {
                throw new Error(resData.error || 'Creation failed');
            }
            
            allInstancesCache = null; // Invalidate global search cache
            showToast('Linked child instance created!', 'success');
            addChildModal.style.display = 'none';
            loadInstanceDetails(activeInstance);
        } catch (err) {
            showToast(`Creation failed: ${err.message}`, 'error');
        } finally {
            addChildConfirmBtn.disabled = false;
            addChildConfirmBtn.textContent = 'Add Child';
        }
    });

    // Global Search Auto-complete & Auto-navigation
    let globalSearchDebounce = null;
    if (globalSearchInput) {
        globalSearchInput.addEventListener('input', () => {
            clearTimeout(globalSearchDebounce);
            const query = globalSearchInput.value.trim().toLowerCase();
            if (!query) {
                if (globalSearchResults) globalSearchResults.style.display = 'none';
                return;
            }
            globalSearchDebounce = setTimeout(async () => {
                try {
                    if (!allInstancesCache) {
                        const res = await fetch('/api/v1.0/get_class_instance_summaries/');
                        if (res.ok) {
                            allInstancesCache = await res.json();
                        } else {
                            allInstancesCache = [];
                        }
                    }
                    const matches = allInstancesCache.filter(inst => 
                        (inst.label && inst.label.toLowerCase().includes(query)) ||
                        (inst.id && inst.id.toLowerCase().includes(query))
                    ).slice(0, 15);

                    if (matches.length === 0) {
                        globalSearchResults.innerHTML = '<div class="global-search-item"><span class="item-sub">No matching instances found</span></div>';
                    } else {
                        globalSearchResults.innerHTML = matches.map(inst => `
                            <div class="global-search-item" data-id="${escapeHtml(inst.id)}" data-type="${escapeHtml(inst.types[0] || '')}">
                                <span class="item-title">${escapeHtml(inst.label)}</span>
                                <span class="item-sub">ID: ${escapeHtml(inst.id)} | Class: ${escapeHtml(inst.types.join(', '))}</span>
                            </div>
                        `).join('');
                    }
                    globalSearchResults.style.display = 'block';

                    document.querySelectorAll('.global-search-item[data-id]').forEach(item => {
                        item.addEventListener('click', () => {
                            const instId = item.getAttribute('data-id');
                            const targetType = item.getAttribute('data-type');
                            globalSearchResults.style.display = 'none';
                            globalSearchInput.value = '';
                            if (targetType) {
                                selectClass(targetType);
                            }
                            navigateToInstance(instId);
                        });
                    });
                } catch (err) {
                    console.error('Global search error:', err);
                }
            }, 200);
        });
    }

    document.addEventListener('click', (e) => {
        if (globalSearchInput && globalSearchResults && !globalSearchInput.contains(e.target) && !globalSearchResults.contains(e.target)) {
            globalSearchResults.style.display = 'none';
        }
    });

    // Initialize Page
    verifyHealth();
    loadClassHierarchy();
});
