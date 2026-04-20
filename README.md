# ConnectWise Receiving Dashboard

A modern, dark-themed web application for managing product receipts in ConnectWise. Streamline your receiving workflow by viewing pending purchase orders, tracking shipments, and recording received quantities—all in one intuitive dashboard.

## Features

- **Real-time Pending Receipts**: View all open purchase orders with pending line items
- **Customer Grouping**: Items organized by customer company for easy reference
- **Quick Receive**: Batch or individual item receiving with quantity controls
- **Serial Number Tracking**: Optional serial number capture and storage
- **Search & Filter**: Quickly find items by PO, customer, product, or vendor
- **Auto-refresh**: Background updates every 5 minutes
- **Dark Theme UI**: Modern, low-glare interface designed for warehouse environments
- **SSL Verification Control**: Support for secure and insecure environments

## Tech Stack

- **Backend**: Flask 3.0.3 with Python 3.12
- **Server**: Gunicorn (2 workers, graceful shutdown support)
- **Frontend**: Vanilla JavaScript, HTML5, CSS3
- **API**: ConnectWise REST API v4.6
- **Containerization**: Docker & Docker Compose

## Prerequisites

### Local Development
- Python 3.12+
- pip
- ConnectWise API credentials (Company ID, Public Key, Private Key, Client ID)

### Docker Deployment
- Docker & Docker Compose
- ConnectWise API credentials

## Installation

### Option 1: Docker Compose (Recommended)

Edit `docker-compose.yml` and update these values:

```yaml
   environment:
     - CW_SITE=api-eu.myconnectwise.net          # Your region
     - CW_COMPANY=yourcompanyid                  # Your ConnectWise company ID
     - CW_PUBLIC_KEY=your_public_key_here        # Your API public key
     - CW_PRIVATE_KEY=your_private_key_here      # Your API private key
     - CW_CLIENT_ID=your_client_id_here          # Your API client ID
     - CW_VERIFY_SSL=true                        # Set to false for self-signed certs
   ```

**Start the application**:
   ```bash
   docker-compose up -d
   ```
**Access the dashboard**:
   - Open browser: `http://localhost:8089`


## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CW_SITE` | `api-eu.myconnectwise.net` | ConnectWise API endpoint (EU/US) |
| `CW_COMPANY` | `` | Your ConnectWise company ID |
| `CW_PUBLIC_KEY` | `` | API public key |
| `CW_PRIVATE_KEY` | `` | API private key |
| `CW_CLIENT_ID` | `` | API client ID |
| `CW_VERIFY_SSL` | `true` | Enable/disable SSL verification |
| `HTTPS_PROXY` | `` | Optional HTTPS proxy URL |

### Finding Your ConnectWise Credentials

1. Log in to ConnectWise
2. Navigate to **System** → **Setup Tables** → **API Keys**
3. Create or locate your API key
4. Copy the following values:
   - **Company ID**: Your ConnectWise company identifier
   - **Public Key**: Found in API key settings
   - **Private Key**: Found in API key settings
   - **Client ID**: The application ID for this integration

## API Endpoints

### GET `/api/pending-receipts`
Fetches all open purchase orders with pending line items.

**Response**:
```json
{
  "items": [
    {
      "poId": 12345,
      "poNumber": "PO-00001",
      "vendor": "Tech Supplies Inc",
      "lineItemId": 67890,
      "description": "Network Switch 48-Port",
      "quantity": 5,
      "received": 2,
      "pending": 3,
      "soId": 54321,
      "company": "ACME Corp"
    }
  ]
}
```

### POST `/api/receive-item`
Records receipt of items for a purchase order line item.

**Request**:
```json
{
  "poId": 12345,
  "lineItemId": 67890,
  "currentReceived": 2,
  "qtyToReceive": 3,
  "serialNumbers": "SN001,SN002,SN003"
}
```

### POST `/api/receive-items`
Receives multiple purchase order line items in a single request.

**Request**:
```json
{
  "items": [
    {
      "poId": 12345,
      "lineItemId": 67890,
      "currentReceived": 2,
      "qtyToReceive": 1,
      "serialNumbers": "SN004"
    }
  ]
}
```

**Response**:
```json
{
  "success": true,
  "processed": 1,
  "failed": 0,
  "results": [
    {
      "lineItemId": 67890,
      "success": true
    }
  ]
}
```

**Response**:
```json
{
  "success": true,
  "updatedItem": { /* Updated line item object */ }
}
```

## Features Explained

### Search & Filter
- Type in the search box to filter by:
  - Customer company name
  - PO number
  - Product description
  - Vendor name

### Receiving Items
1. Select quantity to receive (defaults to pending amount)
2. Optionally enter serial numbers (comma-separated)
3. Click **Receive** button
4. The row is removed immediately for a smoother flow, then dashboard data is refreshed in the background

### Auto-Refresh
- Dashboard automatically refreshes every 5 minutes
- Manual refresh available via **Refresh Queue** button

## Troubleshooting

### "Error loading data: 401 Unauthorized"
- Verify API credentials are correct
- Check that CW_COMPANY, CW_PUBLIC_KEY, CW_PRIVATE_KEY, and CW_CLIENT_ID are set
- Ensure the API key is still active in ConnectWise

### "Error loading data: Connection timeout"
- Check network connectivity to ConnectWise API
- Verify `CW_SITE` is correct for your region (api-eu, api-us, etc.)
- Check if HTTPS_PROXY is required in your environment

### "Error loading data: SSL: CERTIFICATE_VERIFY_FAILED"
- Set `CW_VERIFY_SSL=false` in docker-compose.yml (not recommended for production)
- Or update CA certificates on the host system

### Items not appearing
- Verify purchase orders have `closedFlag = false`
- Check that line items have `receivedQuantity < quantity`
- Ensure line items are not cancelled


## Development

## Performance

- **Gunicorn Workers**: 2 (configurable in Dockerfile)
- **Request Timeout**: 90 seconds
- **Page Size**: 100 items per API request (with pagination)
- **Auto-refresh Interval**: 5 minutes
- **Memory Usage**: ~150-200 MB per container
- **CPU Usage**: Minimal idle, 10-50% during API calls

## Security

- **SSL Verification**: Enabled by default (set `CW_VERIFY_SSL=false` only if necessary)
- **Basic Auth**: ConnectWise credentials encoded in Authorization header
- **HTTPS Proxy Support**: Environment variable configuration
- **Secrets Management**: Use Docker secrets or environment management services in production
