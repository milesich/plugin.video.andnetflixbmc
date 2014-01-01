#!/usr/bin/python
# -*- coding: utf-8 -*-
import urllib
import urllib2
import cookielib
import sys
import re
import os
import json
import time
import shutil
import xbmcplugin
import xbmcgui
import xbmcaddon

dbg = True
dbglevel = 5
pluginhandle = int(sys.argv[1])
addon = xbmcaddon.Addon(id='plugin.video.andnetflixbmc')
addonID = addon.getAddonInfo('id')
cookiejar = cookielib.LWPCookieJar()
opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookiejar))

import CommonFunctions
common = CommonFunctions
common.plugin = addon.getAddonInfo('name') + ' ' + addon.getAddonInfo('version')

addonUserDataFolder = xbmc.translatePath("special://profile/addon_data/"+addonID)
cookieFile = xbmc.translatePath("special://profile/addon_data/"+addonID+"/cookies")
profileFile = xbmc.translatePath("special://profile/addon_data/"+addonID+"/profile")
authFile = xbmc.translatePath("special://profile/addon_data/"+addonID+"/authUrl")
tempFile = xbmc.translatePath("special://profile/addon_data/"+addonID+"/temp.log")
localeFile = xbmc.translatePath("special://profile/addon_data/"+addonID+"/locale")
cacheFolder = os.path.join(addonUserDataFolder, "cache")
cacheFolderCovers = os.path.join(cacheFolder, "covers")
cacheFolderFanart = os.path.join(cacheFolder, "fanart")

username = addon.getSetting("username")
password = addon.getSetting("password")
singleProfile = addon.getSetting("singleProfile") == "true"
showProfiles = addon.getSetting("showProfiles") == "true"

nflxPath = "nflx://www.netflix.com/browse?q="
nflxActionGenre = "g"
nflxActionViewDetails = "view_details"
nflxActionPlay = "play"
nflxParamGenreId = "genreid"
nflxParamMovieId = "movieid"
nflxParamTargetId = "targetid"
nflxPathMovies = "/movies/"
nflxPathShows = "/series/"

webMovies = "http://movies.netflix.com"
webSignin = "https://signup.netflix.com/Login"
webGlobal = "https://signup.netflix.com/global"
webError = webMovies + "/Error"
webProfilesGate = "https://movies.netflix.com/ProfilesGate"

if not os.path.isdir(addonUserDataFolder):
    os.mkdir(addonUserDataFolder)
if not os.path.isdir(cacheFolder):
    os.mkdir(cacheFolder)
if not os.path.isdir(cacheFolderCovers):
    os.mkdir(cacheFolderCovers)
if not os.path.isdir(cacheFolderFanart):
    os.mkdir(cacheFolderFanart)
if os.path.exists(cookieFile):
    cookiejar.load(cookieFile)
if os.path.exists(authFile):
    fh = common.openFile(authFile, 'r')
    auth = fh.read()
    fh.close()


while (username == "" or password == ""):
    addon.openSettings()
    username = addon.getSetting("username")
    password = addon.getSetting("password")


def translation(id):
    return addon.getLocalizedString(id).encode('utf-8')


def dialogError(title, message):
    dialog = xbmcgui.Dialog()
    dialog.ok(title, message[:53], message[53:110], message[110:])


def dialogErrorResult(result, message):
    result['content'] = '' # do not log the content
    result['header'] = '' # do not log headers
    common.log(json.dumps(result))
    dialogError("Error", message)


def login():
    result = common.fetchPage({'link': webSignin})
    
    if result["status"] != 200:
        dialogErrorResult("Unable to connect to Netflix")
        return False

    if result['new_url'].startswith(webGlobal) or "nonSupportedCountry" in result['new_url']:
        # Netflix is not available in my country
        dialogError("Error", translation(30126))
        return False

    if result['new_url'].startswith(webMovies):
        # We are already logged in and were redirected to the homepage
        return True
    
    form = common.parseDOM(result['content'], "form", attrs = {'id': 'login-form'})
    ret = common.parseDOM(form, "input", attrs = {"type": "hidden", "name": "authURL"}, ret = "value")
    if not ret:
        #TODO: this is not a login page and I do not know what to do
        dialogErrorResult(result, "Unknown Error [noform]")
        return False
    
    authUrl = ret[0]
    fh = common.openFile(authFile, "w")
    fh.write(authUrl)
    fh.close()
    
    # Lets try to login
    result = common.fetchPage({"link": webSignin, "post_data": {"authURL": authUrl, "email": username, "password": password, "RememberMe": "on"}})
        
    if result["status"] != 200:
        dialogErrorResult("Unable to connect to Netflix")
        return False

    if result['new_url'].startswith(webMovies):
        # Login successful save cookie
        cookiejar.save(cookieFile)
        return True

    if result['new_url'].startswith(webProfilesGate):
        # Login successful, choose profile
        return chooseProfile(result['content'])

    if result['new_url'] == webSignin:
        # Looks like we have an error
        errors = common.parseDOM(result['content'], "div", attrs = {"id": "aerrors"})
        ret = common.parseDOM(errors, "li")
        if not ret:
            # we should not be here
            dialogErrorResult(result, "Unknown Error [onsignin]")
            return False

        dialogError("Login Error", ret[0])
        return False

    # If we are here then its a problem
    dialogErrorResult(result, "Unknown Error [end]")
    return False


def chooseProfile(content = False):
    if not content:
        result = common.fetchPage({"link": webProfilesGate + "?nextpage=http%3A%2F%2Fmovies.netflix.com%2FDefault"})
    
        if result["status"] != 200:
            dialogErrorResult("Unable to connect to Netflix")
            return False
            
        content = result['content'];
    
    match = re.compile('"profileName":"(.+?)".+?token":"(.+?)"', re.DOTALL).findall(content)
    profiles = []
    tokens = []
    for p, t in match:
        profiles.append(p)
        tokens.append(t)
    dialog = xbmcgui.Dialog()
    nr = dialog.select(translation(30113), profiles)
    if nr >= 0:
        token = tokens[nr]
        # Profile selection isn't remembered, so it has to be executed before every requests (setProfile)
        # If you know a solution for this, please let me know
        # opener.open("https://api-global.netflix.com/desktop/account/profiles/switch?switchProfileGuid="+token)
        fh = common.openFile(profileFile, 'w')
        fh.write(token)
        fh.close()
        cookiejar.save(cookieFile)
        return True
        
    dialogError("Error", "No profiles found")
    return False



def index():
    if login():
        addDir(translation(30002), webMovies + "/MyList?leid=595&link=seeall", 'myList', "")
        xbmcplugin.endOfDirectory(pluginhandle)


def addDir(name, url, mode, iconimage):
    u = sys.argv[0]+"?url="+urllib.quote_plus(url)+"&mode="+str(mode)+"&thumb="+str(iconimage)
    ok = True
    liz = xbmcgui.ListItem(name, iconImage="DefaultTVShows.png", thumbnailImage=iconimage)
    liz.setInfo(type="video", infoLabels={"title": name})
    entries = []
    if "/MyList" in url:
        entries.append((translation(30122), 'RunPlugin(plugin://plugin.video.andnetflixbmc/?mode=addMyListToLibrary)',))
    if not singleProfile:
        entries.append((translation(30110), 'RunPlugin(plugin://plugin.video.andnetflixbmc/?mode=chooseProfile)',))
    liz.addContextMenuItems(entries)
    ok = xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=u, listitem=liz, isFolder=True)
    return ok


index()
