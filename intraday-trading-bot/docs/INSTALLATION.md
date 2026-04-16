# Installation & Deployment Guide

## Deployment Options

### Option 1: Standalone (Recommended)
This is the simplest method. The entire application is bundled into a single file.

1.  Navigate to the `intraday-trading-bot` directory.
2.  Double-click `index.html`.
3.  The application will launch in your default web browser.

### Option 2: Local Server (Python)
If you prefer running via localhost to avoid local file restrictions or for development:

```bash
# Navigate to project directory
cd intraday-trading-bot

# Start Python HTTP Server
python -m http.server 8000
```

Then visit [http://localhost:8000](http://localhost:8000) in your browser.

### Option 3: Static Hosting
Since this is a client-side only application, it can be hosted on any static site provider for free:

- **GitHub Pages**: Push this folder to a GitHub repository and enable Pages.
- **Netlify / Vercel**: Drag and drop the `intraday-trading-bot` folder into their deployment dashboard.
- **AWS S3**: Upload `index.html` to a public S3 bucket.

## Browser Compatibility

| Browser | Version | Support |
| :--- | :--- | :--- |
| **Chrome / Edge** | 90+ | Full Support |
| **Firefox** | 88+ | Full Support |
| **Safari** | 14+ | Full Support |
| **Mobile Safari** | iOS 14+ | Full Support |
| **Internet Explorer** | All | Not Supported |

## Troubleshooting

- **Bot not starting**: Ensure JavaScript is enabled in your browser settings.
- **Visual Glitches**: Check that you are not using a high-contrast mode extension that might conflict with the dark theme.
