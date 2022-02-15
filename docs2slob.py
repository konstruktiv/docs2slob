#!/usr/bin/env python

"""
docs2slob.py - convert documentation from DevDocs to offline Slob dictionaries

Copyright 2022 by konstruktiv
"""

import argparse
from bs4 import BeautifulSoup
import json
import os
import re
import requests
import slob
import sys
import time
from urllib.parse import urljoin


CONTENT_TYPE = "text/html;charset=utf-8"
COPYRIGHT_NOTICE = "Copyright by the original authors of the %s documentation. Thanks to DevDocs (https://www.devdocs.io) for providing the documentation."
TSEP = "-"              # token separator
LTSEP = '~'             # leading token separator
COMPAT_DSEP = ":"       # directory (slash) separator, don't use: / 


parser = argparse.ArgumentParser("doc2slob.py - convert documentation from DevDocs to offline Slob dictionaries")

parser.add_argument("-l", "--list", dest="LIST", action="store_true",
                    help="list documentations available on devdocs.io")

parser.add_argument("-s", "--slug", dest="SLUG", action="store", default=None,
                    help="slug of the documentation listed on devdocs.io")

parser.add_argument("-d", "--download", dest="DOWNLOAD", action="store_true",
                    help="download documentation from devdocs.io")

parser.add_argument("--docdir", dest="DOCDIR", action="store", metavar="DIRECTORY",
                    help="directory of downloaded DevDocs files")

parser.add_argument("--outdir", dest="OUTDIR", action="store", metavar="DIRECTORY",
                    help="output directory for generated Slob files")

parser.add_argument("-g", "--generate", dest="GENERATE", action="store_true",
                    help="generate Slob file(s)")

parser.add_argument("-c", "--compat", dest="COMPAT", action="store_true", default=False,
                    help="processes links and keys for compatibility")

parser.add_argument("-t", "--tokenize", dest="TOKENIZE", action="store_true", default=False,
                    help="split keys for easier lookups")

parser.add_argument("-e", "--external", dest="EXT", action="store", metavar="PREFIX", default="",
                    help="prefix a string to external links")

parser.add_argument("-f", "--filter", dest="FILTER", action="store", metavar="CSV", default="",
                    help="comma separated list of filtered tokens")

class Converter:
    def __init__(self, docdir, outdir, ext, tokenize, slug, compat, filtered):
        self.docdir = docdir
        self.outdir = outdir
        self.ext = ext
        self.tokenize = tokenize
        self.slug = slug
        self.compat = compat
        self.filtered = filtered

    def generate_docs(self):
        if self.slug:
            if os.path.isdir(self.docdir + self.slug):
                print("Processing documentation for %s from %s" % (self.slug, self.docdir+self.slug))
                self.create_slob(self.docdir+self.slug, self.outdir+self.slug)
            else:
                print("Documentation directory does not exist: " + self.docdir + self.slug)
                return
        else:
            for slug in next(os.walk(self.docdir))[1]:
                print("Processing documentation for %s from %s" % (self.slug, self.docdir+slug))
                try:
                    self.create_slob(self.docdir+slug, self.outdir+slug)
                except SystemExit as e:
                    print(e)
                    pass        
    
    def create_slob(self, slugdir, slobname):
        start_time = time. time()
        with slob.create(slobname + ".slob") as slobfile:
            with open(slugdir +"/meta.json") as f:
                meta = json.load(f)
            
            with open(slugdir +"/db.json") as f:
                db = json.load(f)
                for n, key in enumerate(db):
                    self.add_entry(slobfile, key, db[key])
                print("Generated %s.slob from %s entries in %.2f seconds." % (slobname, n+1, (time.time() - start_time)))
    
            slobfile.tag("label", meta["name"])
            if hasattr(meta, "links"):
                slobfile.tag("source", meta["links"]["home"])
            if hasattr(meta, "release"):
                slobfile.tag("version", meta["release"])
            
            slobfile.tag("copyright", COPYRIGHT_NOTICE %(meta["name"]))

    def add_entry(self, slobfile, key, entry):       
        soup = BeautifulSoup(entry, "html.parser")
        
        def cleanup(s): # replace white spaces, underscores
            if not self.tokenize or self.compat:
                return s
            s = re.sub(r"\s+", TSEP, s)
            s = s.replace("_", TSEP).rstrip(TSEP).lstrip(TSEP)       
            return s
    
        def compatible_cleanup(s):  # replace slashes, remove hashes 
            if "#" in s and s.split("#")[0]:
                s = s.split("#")[0]        
            s = s.replace("/", COMPAT_DSEP)       
            return cleanup(s)
    
        has_links = False    
        for a in soup.find_all("a"):
            has_links = True
                
            if self.ext and a.get("href") and a["href"].startswith(("http://", "https://")):
                a.string = self.ext + a.text
            elif self.compat:
                if a.get("title"):
                    del a["title"]
                if a.get("href"):
                    a["href"] = compatible_cleanup(urljoin(key, a["href"]))
            elif a.get("href"):
                a["href"] = urljoin(key, cleanup(a["href"]))
                
        if has_links:
            entry = soup
            
        if not self.compat:
            key = cleanup(key)
        else:
            key =  compatible_cleanup(key)
        
        if not self.tokenize:
            slobfile.add(entry.encode("utf-8"), key, content_type=CONTENT_TYPE)
        else:
            filtered = [t.lower().strip() for t in self.filtered.split(",")] if self.filtered else []
            
            key_tokens = []
            
            if not self.compat:
                sk = re.split(re.escape(TSEP) + "|/", key) 
            else:  
                sk = re.split(re.escape(TSEP) + "|" + re.escape(COMPAT_DSEP), key)
            
            for i in range(1, len(sk)):
                if not sk[i].lower() in filtered:
                    key_tokens.append(sk[i] + LTSEP + key)
            keys = set([key] + key_tokens) # original key used for referencing, key_tokens for manual lookups
    
            slobfile.add(entry.encode("utf-8"), *keys, content_type=CONTENT_TYPE)
            
def list_docs():
    url = "https://devdocs.io"
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(e)
        sys.exit()
    
    devdocs_io_html = response.text
    soup = BeautifulSoup(devdocs_io_html, features="html.parser")
    
    for script in soup.findAll("script"):
        if "/assets/docs-" in str(script) :
            list_js = requests.get(url + "/" + script["src"]).text
    
    list_js = list_js.replace("app.DOCS = ", "", 1)
    list_js = list_js[::-1].replace(";","",1)[::-1]
    list_js = list_js.replace("\\xd6", "Ö")
    list_js = re.sub("\n(\w[a-z_]*)", r'\n"\1"', list_js)
    list_json = json.loads(list_js)

    rows = [["TITLE", "SLUG", "VERSION", "RELEASE"]]
    for doc in list_json:
        row = []
        row.append(doc["name"])
        row.append(doc["slug"])
        if "version" in doc:
            row.append(doc["version"])
        else:
            row.append("")
        if "release" in doc:
            row.append(doc["release"])
        else:
            row.append("")
        rows.append(row)

    for row in rows:
        title, slug, version, release = row
        print ("{:<25} \033[92m{:<25}\033[0m {:<10} {:<10}".format( title, slug, version, release))

def download_docs(docdir, slug):
    dldir = (docdir + "/" + slug).replace("//", "/")
    base_url = "https://documents.devdocs.io/" + slug
    meta_url = base_url + "/meta.json"
    db_url = base_url + "/db.json"

    try:
        for url in [meta_url, db_url]:
            res = requests.get(url)
            res.raise_for_status()
            data = res.content

            if not os.path.exists(dldir):
                os.makedirs(dldir)

            with open(dldir + "/" + url.split("/")[-1], "wb") as f:
                f.write(data)

        print("Downloaded documentation for %s to: %s" % (slug, dldir))

    except requests.exceptions.HTTPError as e:
        print("Download failed. Is the --slug argument correct? Exception:\n" + str(e) )

if __name__ == "__main__":
    if len(sys.argv) > 1:
        args = parser.parse_args()

        if args.LIST:
            list_docs()

        if args.DOWNLOAD:
            if not args.SLUG:
                print("--download option requires --slug argument")
                exit()

            if args.DOCDIR:
                download_docs(args.DOCDIR, args.SLUG)
            else:
                print("--docdir requires existing download directory as argument")
                exit()

        if args.GENERATE:
            if args.DOCDIR and args.OUTDIR:
                converter = Converter(args.DOCDIR, args.OUTDIR, args.EXT, args.TOKENIZE, args.SLUG, args.COMPAT, args.FILTER)
                converter.generate_docs()

            elif not args.DOCDIR:
                print("--docdir requires existing download directory as argument")
                exit()

            elif not args.OUTDIR:
                print("--outdir requires existing output directory as argument")
                exit()
    else:
        parser.print_help()
