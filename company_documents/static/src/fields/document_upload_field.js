import { useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { FileInput } from "@web/core/file_input/file_input";
import { BinaryField, binaryField } from "@web/views/fields/binary/binary_field";

/**
 * Binary field that uploads the file as multipart to /company-documents/upload
 * and only keeps the returned attachment id on the record. The standard
 * binary widget puts the base64 content in the onchange / save JSON-RPC
 * calls, which runs Safari out of memory on large files.
 */
export class DocumentUploadField extends BinaryField {
    static template = "company_documents.DocumentUploadField";
    static components = { FileInput };
    static props = {
        ...BinaryField.props,
        uploadField: { type: String },
    };

    setup() {
        super.setup();
        this.state = useState({ uploading: false });
    }

    get hasFile() {
        const { record, name, uploadField } = this.props;
        return Boolean(record.data[name] || record.data[uploadField]);
    }

    get canDownload() {
        const { record, name } = this.props;
        return record.resId && !record.dirty && record.data[name];
    }

    async beforeOpen() {
        this.state.uploading = false;
        return true;
    }

    onWillUploadFiles(files) {
        this.state.uploading = true;
        return files;
    }

    async onUploaded(files) {
        this.state.uploading = false;
        const file = files[0];
        if (!file) {
            return;
        }
        const { record, fileNameField, uploadField } = this.props;
        await record.update({
            [uploadField]: file.id,
            [fileNameField]: file.filename,
        });
    }

    async onClear() {
        const { record, name, fileNameField, uploadField } = this.props;
        await record.update({
            [name]: false,
            [fileNameField]: false,
            [uploadField]: 0,
        });
    }
}

export const documentUploadField = {
    ...binaryField,
    component: DocumentUploadField,
    extractProps: (fieldInfo) => ({
        ...binaryField.extractProps(fieldInfo),
        uploadField: fieldInfo.options.upload_field || "upload_attachment_id",
    }),
};

registry.category("fields").add("company_document_upload", documentUploadField);
