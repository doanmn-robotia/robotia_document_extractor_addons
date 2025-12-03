/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";


export class UploadArea extends Component {
    static template = "robotia_document_extractor.UploadArea";
    static props = {
        onExtractionComplete: { type: Function, optional: true },
        onUploadStart: { type: Function, optional: true },
        onUploadEnd: { type: Function, optional: true },
        disabled: { type: Boolean, optional: true }
    };

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            documentType: '01',
            uploading: false,
            dragOver: false,
            selectedFile: null, // Store selected file before extraction
            filePreview: null   // Store file info for preview card
        });
    }

    onDragOver(ev) {
        ev.preventDefault();
        // Don't show drag over effect if disabled or already uploading
        if (this.props.disabled || this.state.uploading) {
            return;
        }
        this.state.dragOver = true;
    }

    onDragLeave(ev) {
        ev.preventDefault();
        this.state.dragOver = false;
    }

    onDrop(ev) {
        ev.preventDefault();
        this.state.dragOver = false;

        // Don't handle drop if disabled or already uploading
        if (this.props.disabled || this.state.uploading || this.state.selectedFile) {
            return;
        }

        const files = ev.dataTransfer.files;
        if (files.length > 0) {
            this.onFileSelected(files[0]);
        }
    }

    onFileSelect(ev) {
        const files = ev.target.files;
        if (files.length > 0) {
            this.onFileSelected(files[0]);
        }
        // Reset input so same file can be selected again
        ev.target.value = '';
    }

    onFileSelected(file) {
        // Validate file type
        if (file.type !== 'application/pdf') {
            this.notification.add(
                _t('Please select a PDF file'),
                { type: 'warning' }
            );
            return;
        }

        // Validate file size (max 50MB)
        const maxSize = 50 * 1024 * 1024; // 50MB
        if (file.size > maxSize) {
            this.notification.add(
                _t('File size exceeds 50MB limit'),
                { type: 'warning' }
            );
            return;
        }

        // Store file and show preview card
        this.state.selectedFile = file;
        this.state.filePreview = {
            name: file.name,
            size: this.formatFileSize(file.size),
            sizeBytes: file.size
        };
    }

    cancelFileSelection() {
        this.state.selectedFile = null;
        this.state.filePreview = null;
    }

    async startExtraction() {
        if (!this.state.selectedFile) {
            return;
        }

        const file = this.state.selectedFile;

        // Notify parent that upload is starting
        if (this.props.onUploadStart) {
            this.props.onUploadStart();
        }

        this.state.uploading = true;

        try {
            // Create a URL for the file instead of converting to base64
            const fileUrl = URL.createObjectURL(file);

            // Open Page Selector Client Action
            await this.action.doAction({
                type: 'ir.actions.client',
                tag: 'robotia_document_extractor.page_selector',
                target: 'inline',
                name: _t('Select pages'),
                params: {
                    fileUrl: fileUrl,
                    fileName: file.name,
                    documentType: this.state.documentType
                }
            });

            this.state.uploading = false;
            // Clear selected file after handoff
            this.state.selectedFile = null;
            this.state.filePreview = null;

            // Notify parent that upload has ended
            if (this.props.onUploadEnd) {
                this.props.onUploadEnd();
            }

        } catch (error) {
            console.error('Error starting page selector:', error);
            this.state.uploading = false;

            if (this.props.onUploadEnd) {
                this.props.onUploadEnd();
            }

            this.notification.add(
                _t('Failed to open page selector: %s', error.message || _t('Unknown error')),
                { type: 'danger', sticky: true }
            );
        }
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }



    onDocumentTypeChange(ev) {
        this.state.documentType = ev.target.value;
    }
}
