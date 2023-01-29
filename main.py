import os
import requests
import hashlib
from zipfile import ZipFile
from bs4 import BeautifulSoup
import config

PUBLIC_DIR = os.path.realpath(os.path.dirname(__file__)) + "/public"

class Requests:
    BASE_URL = "https://api.github.com"
    s = requests.Session()

    def __init__(self, token: str):
        self.s.headers['accept'] = 'application/vnd.github.v3+json'
        self.s.headers['Authorization'] = f'Bearer {token}'
        self.s.headers['X-GitHub-Api-Version'] = '2022-11-28'

    def makeRequest(self, endpoint: str, query: dict = {})-> dict:
        r = self.s.get(self.BASE_URL + endpoint, params=query)
        if r.ok:
            return r.json()
        raise Exception('Error sending request')

def getRootXML():
    rootPath = PUBLIC_DIR + "/addons.xml"
    rootXml = ""
    if os.path.exists(rootPath):
        with open(rootPath, 'r') as f:
            rootXml = f.read()
    
    soup = BeautifulSoup(rootXml, features='lxml-xml')

    if not rootXml:
        addons = soup.new_tag('addons')
        soup.append(addons)

    return soup

def pushToRootXML(app: str, version: str, appSoup: BeautifulSoup, rootSoup: BeautifulSoup):
    addons = rootSoup.find('addons')
    if not addons:
        raise Exception("Addons not found")
    
    addon = addons.find('addon', {
        'id': app
    })

    # If addon already exists, check the version, if it's older rewrite with new info
    if addon:
        addon.decompose()
    
    addons.append(appSoup)

def handleAssets(path: str, app: str, soup: BeautifulSoup, archive: ZipFile):
    assets_root = soup.find('assets')

    if not assets_root:
        return
    
    assets = assets_root.findChildren()

    if len(assets) > 0:
        os.makedirs(path + '/resources', exist_ok=True)
        for asset in assets:
            if not os.path.isfile(path + "/" + asset.text):
                art = archive.read(app + "/" + asset.text)
                with open(path + "/" + asset.text, 'wb') as f:
                    f.write(art)

def handleLicense(path: str, app: str, archive: ZipFile):
    try:
        licenseData = archive.read(app + '/LICENSE.txt').decode('utf-8')
    except KeyError:
        return

    licenseFile = path + "/LICENSE.txt"
    if not os.path.isfile(licenseFile):
        with open(licenseFile, 'w') as f:
            f.write(licenseData)

def handlePluginVersion(root: BeautifulSoup, url: str, app: str, version: str, zipName: str):
    versionPath = PUBLIC_DIR + '/' + app
    zipPath = versionPath + '/' + zipName

    if os.path.isfile(zipPath):
        return

    os.makedirs(versionPath, exist_ok=True)
    hs = hashlib.md5()
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(zipPath, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                hs.update(chunk) # Building hash
                f.write(chunk) # Building file

    with open(zipPath + '.md5', 'w') as fc:
        fc.write(hs.hexdigest() + " *" + zipName)
    
    # Zip file
    with ZipFile(zipPath, 'r') as archive:
        xml = archive.read(app + '/addon.xml').decode('utf-8')
        with open(versionPath + '/addon.xml', 'w') as f:
            f.write(xml)

        soup = BeautifulSoup(xml, features='lxml-xml')
        handleAssets(versionPath, app, soup, archive)
        handleLicense(versionPath, app, archive)
        pushToRootXML(app, version, soup, root)

def main():
    requests = Requests(config.GITHUB_TOKEN)
    root = getRootXML()
    for repo in config.REPOS:
        releases = requests.makeRequest(f'/repos/{repo[0]}/{repo[1]}/releases')
        release = releases[0]
        version = release['tag_name'][1:]
        zipUrl = release['assets'][0]['browser_download_url']

        zipName = repo[1] + '-' + version + '.zip'

        handlePluginVersion(root, zipUrl, repo[1], version, zipName)
    
    # Write root xml and checksum
    rootStr = str(root)
    with open(PUBLIC_DIR + '/addons.xml', 'w') as f:
        f.write(rootStr)
    
    rootHash = hashlib.md5(rootStr.encode())
    with open(PUBLIC_DIR + "/addons.xml.md5", 'w') as f:
        f.write(rootHash.hexdigest() + "  " + "addons.xml")

if __name__ == '__main__':
    main()
