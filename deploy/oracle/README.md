# DungeonTuber on Oracle Cloud (Always Free) with DuckDNS

Ampere A1 VM + Docker + Caddy (HTTPS) + DuckDNS name. No other cloud service needed.

## 1. DuckDNS
1. Sign in at https://www.duckdns.org and create a subdomain (`yourname` -> `yourname.duckdns.org`).
2. Note the token shown on the page. The `duckdns` container in the compose file keeps the IP up to date.

## 2. Oracle Cloud
1. Reserve a public IP (Networking > Reserved public IPs) so it does not change when the VM is replaced.
2. Create the instance: shape `VM.Standard.A1.Flex` (up to 2 OCPU / 12 GB), Ubuntu 24.04 aarch64, public subnet, assign the
   reserved IP, add your SSH key, boot volume up to 200 GB.
3. Security List of the subnet: add ingress rules (source `0.0.0.0/0`, TCP) for ports **80** and **443**. Port 22 is there by default.
4. Ubuntu images on OCI also block traffic with iptables; open the ports on the VM:
   ```bash
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
   sudo netfilter-persistent save
   ```

## 3. On the VM
```bash
curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker $USER   # log out and in again
git clone -b web-version https://github.com/gandulf/DungeonTuber.git && cd DungeonTuber/deploy/oracle   # drop -b once merged to master
nano .env                                                                      # see below
mkdir -p music && sudo chown -R 1000:1000 music
docker compose up -d
```
`.env` (git ignores it, do not commit it):
```
DOMAIN=yourname.duckdns.org
DUCKDNS_SUBDOMAIN=yourname
DUCKDNS_TOKEN=token-from-duckdns.org
DT_PASSWORD=choose-a-password
```

Open `https://<DOMAIN>`. Copy your mp3s into `music/`
(or add an S3 library under Settings > Library) and use *Rescan Library* in the menu.

## Notes
- WiZ lights are not reachable from a cloud VM (UDP broadcast into your LAN): run the [WiZ light agent](../../agents/wiz/README.md) in your home network, it connects out to the server.
- Oracle reclaims idle Always Free instances (7 days below 20 % CPU/network/memory); check the instance now and then.
- Back up the `dt-data` volume (`library.db`, `settings.json`) now and then:
  `docker run --rm -v oracle_dt-data:/data -v $PWD:/out alpine tar czf /out/dt-data.tgz -C /data .`
  (the volume name is `<folder>_dt-data`, see `docker volume ls`).
- Updates are automatic: [What's up Docker](https://getwud.github.io/wud/) (`wud` service) checks every hour whether `ghcr.io/gandulf/dungeontuber:latest`
  has a new image, pulls it and recreates the container; the settings and the database live in the `dt-data` volume. See what it did with
  `docker compose logs wud`. To update right away: `docker compose pull dungeontuber && docker compose up -d`. For a private image add
  registry credentials (`WUD_REGISTRY_GHCR_PUBLIC_...`, see the WUD docs); to pin a version use that tag instead of `latest` and remove the labels.
- Changes of the compose file or `.env`: `git pull && docker compose up -d`.
