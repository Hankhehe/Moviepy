document.addEventListener('DOMContentLoaded', () => {
    const templatesGrid = document.getElementById('templatesGrid');
    const workspaceSection = document.getElementById('workspaceSection');
    const formContainer = document.getElementById('formContainer');
    const dynamicFields = document.getElementById('dynamicFields');
    const renderForm = document.getElementById('renderForm');
    const templateIdInput = document.getElementById('templateIdInput');
    const workspaceTitle = document.getElementById('workspaceTitle');
    const submitBtn = document.getElementById('submitBtn');
    
    const progressContainer = document.getElementById('progressContainer');
    const progressPercentage = document.getElementById('progressPercentage');
    const progressStatusMsg = document.getElementById('progressStatusMsg');
    const progressBarFill = document.getElementById('progressBarFill');
    
    const resultContainer = document.getElementById('resultContainer');
    const resultVideoPlayer = document.getElementById('resultVideoPlayer');
    const downloadBtn = document.getElementById('downloadBtn');
    const resetBtn = document.getElementById('resetBtn');

    let templates = [];
    let selectedTemplate = null;
    let pollInterval = null;
    let selectedFilesMap = {}; // Tracks selected files for drag & drop zones

    // 1. Fetch available templates
    async function loadTemplates() {
        try {
            const res = await fetch('/api/templates');
            if (!res.ok) throw new Error('無法取得範本資料');
            templates = await res.json();
            renderTemplates();
        } catch (error) {
            templatesGrid.innerHTML = `
                <div style="text-align: center; grid-column: 1/-1; padding: 3rem; color: #f87171;">
                    載入範本失敗: ${error.message}
                </div>
            `;
        }
    }

    // 2. Render templates in grid
    function renderTemplates() {
        templatesGrid.innerHTML = '';
        templates.forEach(tpl => {
            const card = document.createElement('div');
            card.className = 'template-card';
            card.innerHTML = `
                <div class="video-preview-wrapper">
                    <video src="${tpl.preview_url}" autoplay loop muted playsinline></video>
                </div>
                <div class="template-card-info">
                    <h3>${tpl.name}</h3>
                    <p>${tpl.description}</p>
                    <button class="select-template-btn" data-id="${tpl.id}">
                        使用此範本
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
                    </button>
                </div>
            `;
            
            // Add click listener
            card.querySelector('.select-template-btn').addEventListener('click', () => {
                selectTemplate(tpl.id);
            });
            
            templatesGrid.appendChild(card);
        });
    }

    // 3. Select a template and build the form
    function selectTemplate(templateId) {
        selectedTemplate = templates.find(t => t.id === templateId);
        if (!selectedTemplate) return;

        // Reset workspace state
        resetWorkspaceUI();
        
        templateIdInput.value = templateId;
        workspaceTitle.textContent = `製作「${selectedTemplate.name}」`;
        
        // Build form fields
        dynamicFields.innerHTML = '';
        selectedFilesMap = {};

        selectedTemplate.fields.forEach(field => {
            const formGroup = document.createElement('div');
            formGroup.className = 'form-group';
            formGroup.id = `group_${field.name}`;
            
            // Label
            const label = document.createElement('label');
            label.textContent = field.label + (field.required ? ' *' : '');
            formGroup.appendChild(label);
            
            // Input Controls
            if (field.type === 'text') {
                const input = document.createElement('input');
                input.type = 'text';
                input.name = field.name;
                input.className = 'form-input';
                input.placeholder = field.placeholder || '';
                input.required = field.required;
                formGroup.appendChild(input);
            } 
            else if (field.type === 'select') {
                const select = document.createElement('select');
                select.name = field.name;
                select.className = 'form-select';
                select.required = field.required;
                
                field.options.forEach(opt => {
                    const option = document.createElement('option');
                    option.value = opt.value;
                    option.textContent = opt.label;
                    select.appendChild(option);
                });
                
                // Watch for changes (for conditional rendering)
                select.addEventListener('change', () => handleConditionalFields());
                formGroup.appendChild(select);
            } 
            else if (field.type === 'file') {
                const dropzone = document.createElement('div');
                dropzone.className = 'dropzone';
                dropzone.id = `dropzone_${field.name}`;
                dropzone.innerHTML = `
                    <div class="dropzone-icon">↑</div>
                    <p>將檔案拖曳至此，或點擊上傳</p>
                    <span>支援格式: ${field.accept === 'image/*' ? '圖片 (PNG/JPG)' : field.accept === 'video/*' ? '影片 (MP4)' : '音訊 (MP3/WAV)'}</span>
                    <input type="file" class="file-input" name="${field.name}" accept="${field.accept}" ${field.multiple ? 'multiple' : ''} ${field.required ? 'required' : ''}>
                    <div class="file-preview-container" id="preview_${field.name}"></div>
                `;
                
                const fileInput = dropzone.querySelector('.file-input');
                const previewContainer = dropzone.querySelector('.file-preview-container');
                
                // Prevent drag/drop browser defaults
                ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                    dropzone.addEventListener(eventName, e => e.preventDefault(), false);
                });

                // Highlight dropzone on dragover
                ['dragenter', 'dragover'].forEach(eventName => {
                    dropzone.addEventListener(eventName, () => dropzone.classList.add('dragover'), false);
                });
                ['dragleave', 'drop'].forEach(eventName => {
                    dropzone.addEventListener(eventName, () => dropzone.classList.remove('dragover'), false);
                });

                // Handle dropped files
                dropzone.addEventListener('drop', (e) => {
                    const dt = e.dataTransfer;
                    const files = dt.files;
                    handleFiles(files, field, fileInput, previewContainer);
                });

                // Handle clicked files
                fileInput.addEventListener('change', (e) => {
                    const files = e.target.files;
                    handleFiles(files, field, fileInput, previewContainer);
                });

                formGroup.appendChild(dropzone);
            }
            
            dynamicFields.appendChild(formGroup);
        });

        // Setup visibility logic
        handleConditionalFields();

        // Reveal workspace
        workspaceSection.style.display = 'block';
        workspaceSection.scrollIntoView({ behavior: 'smooth' });
    }

    // Handles files selected via click or drag-and-drop
    function handleFiles(files, field, fileInput, previewContainer) {
        if (!files.length) return;
        
        previewContainer.innerHTML = '';
        const filesArray = Array.from(files);
        
        // Store reference
        selectedFilesMap[field.name] = filesArray;
        
        // Update input element files property programmatically for native validation
        const dataTransfer = new DataTransfer();
        filesArray.forEach(file => dataTransfer.items.add(file));
        fileInput.files = dataTransfer.files;

        // Render visual preview
        filesArray.forEach((file, index) => {
            const previewCard = document.createElement('div');
            if (field.accept === 'image/*') {
                previewCard.className = 'file-preview-card image-card';
                const img = document.createElement('img');
                img.src = URL.createObjectURL(file);
                img.onload = () => URL.revokeObjectURL(img.src);
                previewCard.appendChild(img);
            } else {
                previewCard.className = 'file-preview-card';
                previewCard.innerHTML = `
                    <span>📄</span>
                    <span>${file.name.length > 20 ? file.name.substring(0, 17) + '...' : file.name}</span>
                    <span class="remove-file-btn" data-index="${index}">&times;</span>
                `;
                // Add removal logic for non-image list
                previewCard.querySelector('.remove-file-btn').addEventListener('click', (e) => {
                    e.stopPropagation();
                    removeFile(field.name, index, fileInput, previewContainer, field);
                });
            }
            previewContainer.appendChild(previewCard);
        });
    }

    function removeFile(fieldName, index, fileInput, previewContainer, field) {
        let files = selectedFilesMap[fieldName] || [];
        files.splice(index, 1);
        selectedFilesMap[fieldName] = files;
        
        // Sync input files
        const dataTransfer = new DataTransfer();
        files.forEach(file => dataTransfer.items.add(file));
        fileInput.files = dataTransfer.files;

        // Redraw preview
        handleFiles(fileInput.files, field, fileInput, previewContainer);
    }

    // Dynamic visibility of fields depending on select controls
    function handleConditionalFields() {
        if (!selectedTemplate) return;
        
        selectedTemplate.fields.forEach(field => {
            if (field.conditional) {
                // Format of conditional: "fieldName=value"
                const [targetName, targetValue] = field.conditional.split('=');
                const targetElement = document.querySelector(`[name="${targetName}"]`);
                const groupElement = document.getElementById(`group_${field.name}`);
                const fileInputElement = groupElement.querySelector('input[type="file"]');
                
                if (targetElement && groupElement) {
                    if (targetElement.value === targetValue) {
                        groupElement.style.display = 'block';
                        if (fileInputElement) fileInputElement.required = true;
                    } else {
                        groupElement.style.display = 'none';
                        if (fileInputElement) {
                            fileInputElement.required = false;
                            fileInputElement.value = ''; // clear input
                            const preview = groupElement.querySelector('.file-preview-container');
                            if (preview) preview.innerHTML = '';
                        }
                    }
                }
            }
        });
    }

    // 4. Form Submission & API Request
    renderForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const formData = new FormData(renderForm);
        
        // Append files manually from our map to ensure drag-and-drop files are fully captured
        for (const [fieldName, files] of Object.entries(selectedFilesMap)) {
            // Remove the default empty file inputs from formData first
            formData.delete(fieldName);
            
            // Re-append actual files
            files.forEach(file => {
                formData.append(fieldName, file);
            });
        }

        // Show rendering progress UI
        formContainer.style.display = 'none';
        progressContainer.style.display = 'block';
        updateProgress(0, '正在上傳素材，發送剪輯請求...');
        
        submitBtn.disabled = true;

        try {
            const response = await fetch('/api/render', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || '發送渲染請求失敗');
            }

            const data = await response.json();
            const taskId = data.task_id;
            
            // Start Polling Status
            startPolling(taskId);
            
        } catch (error) {
            alert(`發生錯誤: ${error.message}`);
            // Revert back to form
            formContainer.style.display = 'block';
            progressContainer.style.display = 'none';
            submitBtn.disabled = false;
        }
    });

    // 5. Polling Task Progress
    function startPolling(taskId) {
        if (pollInterval) clearInterval(pollInterval);
        
        pollInterval = setInterval(async () => {
            try {
                const res = await fetch(`/api/status/${taskId}`);
                if (!res.ok) throw new Error('查詢任務狀態失敗');
                
                const task = await res.json();
                
                if (task.status === 'pending' || task.status === 'processing') {
                    updateProgress(task.progress, task.message);
                } 
                else if (task.status === 'completed') {
                    clearInterval(pollInterval);
                    showSuccessResult(task.output_url);
                } 
                else if (task.status === 'failed') {
                    clearInterval(pollInterval);
                    alert(`渲染失敗: ${task.message}`);
                    resetWorkspaceUI();
                }
            } catch (error) {
                console.error(error);
                progressStatusMsg.textContent = `連接異常，重試中... (${error.message})`;
            }
        }, 1000);
    }

    function updateProgress(percentage, message) {
        progressPercentage.textContent = `${percentage}%`;
        progressBarFill.style.width = `${percentage}%`;
        progressStatusMsg.textContent = message;
    }

    // 6. Show rendered output video
    function showSuccessResult(videoUrl) {
        progressContainer.style.display = 'none';
        resultContainer.style.display = 'block';
        
        resultVideoPlayer.src = videoUrl;
        resultVideoPlayer.load();
        resultVideoPlayer.play();
        
        downloadBtn.href = videoUrl;
    }

    function resetWorkspaceUI() {
        if (pollInterval) clearInterval(pollInterval);
        formContainer.style.display = 'block';
        progressContainer.style.display = 'none';
        resultContainer.style.display = 'none';
        submitBtn.disabled = false;
        resultVideoPlayer.src = '';
    }

    // 7. Reset all
    resetBtn.addEventListener('click', () => {
        resetWorkspaceUI();
        renderForm.reset();
        selectedFilesMap = {};
        const previews = renderForm.querySelectorAll('.file-preview-container');
        previews.forEach(p => p.innerHTML = '');
        workspaceSection.style.display = 'none';
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });

    // Run on startup
    loadTemplates();
});
