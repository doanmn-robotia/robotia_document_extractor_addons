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
            dragOver: false
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
        if (this.props.disabled || this.state.uploading) {
            return;
        }

        const files = ev.dataTransfer.files;
        if (files.length > 0) {
            this.handleFile(files[0]);
        }
    }

    onFileSelect(ev) {
        const files = ev.target.files;
        if (files.length > 0) {
            this.handleFile(files[0]);
        }
        // Reset input so same file can be selected again
        ev.target.value = '';
    }

    async handleFile(file) {
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

        // Notify parent that upload is starting
        if (this.props.onUploadStart) {
            this.props.onUploadStart();
        }

        this.state.uploading = true;

        try {
            // Read file as base64
            const base64Data = await this.readFileAsBase64(file);

            // Call extraction controller
            const result = await rpc('/document_extractor/extract', {
                pdf_data: base64Data,
                filename: file.name,
                document_type: this.state.documentType
            });

            this.state.uploading = false;

            // Notify parent that upload has ended
            if (this.props.onUploadEnd) {
                this.props.onUploadEnd();
            }

            // Handle result
            if (result.type === 'ir.actions.act_window') {
                // Success - open form with extracted data
                this.notification.add(
                    _t('Document extracted successfully! Please review the data.'),
                    { type: 'success' }
                );

                // Notify parent to reload statistics
                if (this.props.onExtractionComplete) {
                    await this.props.onExtractionComplete();
                }
                await this.action.doAction(result);
            } else if (result.type === 'ir.actions.client') {
                // Error notification already displayed by controller
                await this.action.doAction(result);
            }

        } catch (error) {
            console.error('Extraction error:', error);
            this.state.uploading = false;

            // Notify parent that upload has ended (even on error)
            if (this.props.onUploadEnd) {
                this.props.onUploadEnd();
            }

            this.notification.add(
                _t('Extraction failed: %s', error.message || _t('Unknown error')),
                { type: 'danger', sticky: true }
            );
        }
    }

    readFileAsBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();

            reader.onload = (e) => {
                // Remove the data:application/pdf;base64, prefix
                const base64 = e.target.result.split(',')[1];
                resolve(base64);
            };

            reader.onerror = (error) => {
                reject(error);
            };

            reader.readAsDataURL(file);
        });
    }

    onDocumentTypeChange(ev) {
        this.state.documentType = ev.target.value;
    }
}
