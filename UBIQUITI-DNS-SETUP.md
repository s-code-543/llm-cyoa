# Ubiquiti Router DNS Configuration

Since this Mac is a headless server accessed remotely, configure DNS on your Ubiquiti router instead of /etc/hosts.

## Required DNS Entries

In your Ubiquiti router's DNS settings, add these two A records:

1. **openwebui.mac.stargate.lan** → `<Mac's IP address>`
2. **cyoa.mac.stargate.lan** → `<Mac's IP address>`

Both should point to the same IP address (the Mac server's local network IP).

## Finding Your Mac's IP Address

On the Mac server, run:
```bash
ifconfig | grep "inet " | grep -v 127.0.0.1
```

Or check your Ubiquiti router's DHCP leases for this Mac.

## Ubiquiti Configuration Steps

1. Log into your Ubiquiti UniFi Controller
2. Navigate to: **Settings** → **Networks** → **[Your LAN]** → **DHCP Name Server**
3. Or use: **Settings** → **Services** → **DNS** → **Static DNS Entries**
4. Add the two entries above
5. Save and provision

## Verification

From any machine on your network (not the Mac itself):

```bash
# Test DNS resolution
nslookup openwebui.mac.stargate.lan
nslookup cyoa.mac.stargate.lan

# Test HTTPS access
curl -k https://openwebui.mac.stargate.lan
curl -k https://cyoa.mac.stargate.lan
```

The `-k` flag bypasses certificate validation (acceptable for local mkcert certificates).

## Browser Access

Once DNS is configured:

- OpenWebUI: https://openwebui.mac.stargate.lan
- CYOA Game: https://cyoa.mac.stargate.lan
- CYOA Admin: https://cyoa.mac.stargate.lan/admin/dashboard/

Note: Your browser will need to trust the mkcert CA certificate, or you'll see SSL warnings (which you can bypass for local development).
