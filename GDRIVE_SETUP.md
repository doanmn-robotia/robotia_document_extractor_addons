# Google Drive Integration Setup Guide

This guide explains how to set up automatic PDF fetching and OCR processing from Google Drive.

## Overview

The Google Drive integration enables:
- **Automatic PDF Fetching**: Periodically fetch new PDF files from a specified Google Drive folder
- **Automatic OCR Processing**: Process fetched PDFs using AI extraction (Gemini API)
- **Error Handling**: Retry failed OCR processing automatically
- **Source Tracking**: Distinguish between user-uploaded and externally-fetched documents

## Architecture

### Workflow

1. **Cron Job 1 (Fetch Files)**: Runs every 30 minutes (configurable)
   - Scans configured Google Drive folder for new PDF files
   - Downloads PDFs that haven't been processed yet
   - Creates `document.extraction` records with:
     - `source = 'from_external_source'`
     - `ocr_status = 'pending'`
     - `gdrive_file_id` for tracking

2. **Cron Job 2 (Process OCR)**: Runs every 30 minutes (configurable)
   - Finds documents with `ocr_status` in `['pending', 'error']`
   - Processes up to 3 documents per run (configurable)
   - Extracts data using existing AI extraction service
   - Updates records with extracted data or error messages

### New Fields

The following fields have been added to `document.extraction` model:

- **`source`** (Selection, required):
  - `from_user_upload`: Document uploaded manually by user (default)
  - `from_external_source`: Document fetched from Google Drive

- **`ocr_status`** (Selection):
  - `pending`: Waiting for OCR processing
  - `processing`: Currently being processed
  - `completed`: OCR completed successfully
  - `error`: OCR failed (with error message in `ocr_error_message`)

- **`ocr_error_message`** (Text): Error details if OCR fails
- **`gdrive_file_id`** (Char): Google Drive file ID for tracking

## Installation

### 1. Install Python Dependencies

Activate your virtual environment and install required packages:

```bash
source ../env/bin/activate
pip install google-api-python-client google-auth
```

### 2. Update Odoo Module

Update the module to load new code and data:

```bash
./odoo-bin -c odoo.conf -d <database_name> -u robotia_document_extractor
```

### 3. Create Google Cloud Service Account

#### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Note the project ID

#### Step 2: Enable Google Drive API

1. In Google Cloud Console, go to **APIs & Services > Library**
2. Search for "Google Drive API"
3. Click **Enable**

#### Step 3: Create Service Account

1. Go to **IAM & Admin > Service Accounts**
2. Click **Create Service Account**
3. Enter service account details:
   - Name: `odoo-gdrive-integration` (or any name)
   - Description: "Service account for Odoo document extraction"
4. Click **Create and Continue**
5. Skip "Grant this service account access to project" (optional)
6. Click **Done**

#### Step 4: Create and Download JSON Key

1. Click on the created service account
2. Go to **Keys** tab
3. Click **Add Key > Create new key**
4. Select **JSON** format
5. Click **Create**
6. Save the downloaded JSON file securely (you'll need it later)

#### Step 5: Note the Service Account Email

The JSON file contains a field `client_email` like:
```
odoo-gdrive-integration@your-project-id.iam.gserviceaccount.com
```

You'll need this email to share the Google Drive folder.

### 4. Configure Google Drive Folder

1. Create or select a Google Drive folder for PDF files
2. **Share the folder** with the service account email (from Step 5 above):
   - Right-click folder → Share
   - Add the service account email
   - Give **Viewer** or **Reader** permission (NOT Editor)
3. Get the folder ID from the URL:
   ```
   https://drive.google.com/drive/folders/1A2B3C4D5E6F7G8H9I0J
                                            ^^^^^^^^^^^^^^^^^^^
                                            This is the folder ID
   ```

### 5. Configure Odoo Settings

1. Log in to Odoo as Administrator
2. Go to **Settings > Document Extractor**
3. Scroll to **Google Drive Integration** section
4. Configure the following:

   - **Enable Google Drive Integration**: Check the box
   - **Google Drive Folder ID**: Paste the folder ID (e.g., `1A2B3C4D5E6F7G8H9I0J`)
   - **Service Account JSON**: Paste the entire contents of the downloaded JSON file
   - **Fetch Interval (minutes)**: 30 (default) - how often to check for new files
   - **OCR Batch Size**: 3 (default) - number of documents to process per run

5. Click **Save**

### 6. Enable Cron Jobs

1. Go to **Settings > Technical > Automation > Scheduled Actions**
2. Find these two cron jobs:
   - **Document Extractor: Fetch Files from Google Drive**
   - **Document Extractor: Process Pending OCR**
3. For each cron job:
   - Open the record
   - Check **Active** checkbox
   - Verify **Interval Number** is set to `30` and **Interval Type** is `minutes`
   - Click **Save**

## Usage

### Automatic Processing

Once configured and enabled, the system will automatically:

1. **Every 30 minutes**: Check Google Drive for new PDF files
2. **Every 30 minutes**: Process up to 3 pending documents

### Manual Triggering (for testing)

You can manually trigger the cron jobs:

1. Go to **Settings > Technical > Automation > Scheduled Actions**
2. Open the cron job
3. Click **Run Manually** button

### Monitoring

#### View Documents from External Sources

1. Go to **Document Extractor > Extractions**
2. Apply filter: **External Source (Google Drive)**
3. You'll see all documents fetched from Google Drive

#### Check OCR Status

Apply these filters to monitor OCR processing:

- **OCR Pending**: Documents waiting to be processed
- **OCR Processing**: Documents currently being processed
- **OCR Completed**: Successfully processed documents
- **OCR Error**: Documents that failed processing

#### View Error Details

If a document has `OCR Status = Error`:

1. Open the document record
2. The **OCR Error Message** field contains the error details
3. Fix the issue (if possible)
4. The system will retry automatically on next cron run

## Configuration Options

### Batch Size

Control how many documents to process per run:

- **Low API limits**: Set to 1-2 documents
- **Standard usage**: 3 documents (default)
- **High volume**: 5-10 documents (requires sufficient Gemini API quota)

### Cron Interval

Adjust how often to fetch and process:

- **Low volume**: 60 minutes (1 hour)
- **Standard**: 30 minutes (default)
- **High volume**: 10-15 minutes

**Note**: Both cron jobs run at the same interval.

## Troubleshooting

### Common Issues

#### 1. "Google Drive API libraries not installed"

**Solution**: Install required Python packages:
```bash
pip install google-api-python-client google-auth
```

#### 2. "Google Drive credentials not configured"

**Solution**: Ensure you've pasted the Service Account JSON in Settings.

#### 3. "Invalid Google Drive credentials JSON format"

**Solution**:
- Verify you copied the entire JSON file contents
- Check for extra spaces or line breaks
- Ensure it's valid JSON (starts with `{` and ends with `}`)

#### 4. "Failed to initialize Google Drive service"

**Possible causes**:
- Service account doesn't have access to the folder
- Google Drive API not enabled in Google Cloud project
- Invalid credentials

**Solution**:
- Re-share the folder with the service account email
- Enable Google Drive API in Google Cloud Console
- Re-download and paste the JSON credentials

#### 5. "No files being fetched"

**Check**:
- Folder ID is correct
- Folder contains PDF files
- Folder is shared with service account email
- Cron job is active and running
- Check cron job logs in Odoo logs

#### 6. "OCR Status stuck at 'processing'"

**Solution**:
- Check Odoo server logs for errors
- Ensure Gemini API key is configured
- Check if the cron job completed or crashed
- Reset status to 'pending' manually to retry

### Viewing Logs

Check Odoo logs for detailed error messages:

```bash
tail -f /var/log/odoo/odoo-server.log | grep -i "gdrive\|google drive"
```

### Manual Reset

If documents are stuck in processing state:

```python
# In Odoo shell or developer mode
self.env['document.extraction'].search([
    ('ocr_status', '=', 'processing')
]).write({'ocr_status': 'pending'})
```

## Security Considerations

### Service Account Permissions

- **Use read-only access**: Only grant "Viewer" permission to the service account
- **Don't share credentials**: Keep the JSON file secure and never commit to version control
- **Rotate keys regularly**: Create new service account keys periodically

### Folder Access

- **Dedicated folder**: Use a dedicated folder only for Odoo integration
- **Limited sharing**: Only share with necessary users and the service account
- **Monitor access**: Regularly review who has access to the folder

## Advanced Configuration

### Different Intervals for Fetch vs OCR

Currently, both cron jobs use the same interval. To set different intervals:

1. Go to **Settings > Technical > Automation > Scheduled Actions**
2. Edit each cron job individually
3. Set different **Interval Number** values

Example:
- Fetch: Every 60 minutes (check for new files less frequently)
- OCR: Every 15 minutes (process faster)

### Custom Processing Logic

The OCR processing logic can be customized in:
```
robotia_document_extractor/models/gdrive_service.py
```

Methods:
- `fetch_new_files()`: Fetching logic
- `process_pending_ocr()`: OCR processing logic

## Support

For issues or questions:
- Check Odoo logs for detailed error messages
- Verify all configuration steps
- Review Google Cloud Console for API quota and errors
- Contact your system administrator

## Changelog

### Version 1.5.0
- Added Google Drive integration
- Added automatic PDF fetching
- Added automatic OCR processing
- Added source tracking (`from_user_upload` vs `from_external_source`)
- Added OCR status tracking (`pending`, `processing`, `completed`, `error`)
