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
import subprocess
import shutil
import xbmcplugin
import xbmcgui
import xbmcaddon

dbg = True
dbglevel = 5

import mycookiejar

pluginhandle = int(sys.argv[1])
addon = xbmcaddon.Addon(id='plugin.video.andnetflixbmc')
addonID = addon.getAddonInfo('id')
#cookiejar = cookielib.LWPCookieJar()
cookiejar = mycookiejar.MyCookieJar()
opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookiejar))

import CommonFunctions
common = CommonFunctions
common.plugin = addon.getAddonInfo('name') + ' ' + addon.getAddonInfo('version')
common.USERAGENT = "Mozilla/5.0 (Windows NT 5.1; rv:25.0) Gecko/20100101 Firefox/25.0"

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
    authUrl = fh.read()
    fh.close()
if os.path.exists(profileFile):
    fh = common.openFile(profileFile, 'r')
    profileName = fh.read()
    fh.close()


while (username == "" or password == ""):
    addon.openSettings()
    username = addon.getSetting("username")
    password = addon.getSetting("password")


# Actions

def index():
    if login():
        addDir(translation(30002), webMovies + "/MyList?leid=595&link=seeall", 'listMyVideos', "")
        xbmcplugin.endOfDirectory(pluginhandle)


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
    fh = common.openFile(authFile, u"wb")
    fh.write(common.makeAscii(authUrl))
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


def listMyVideos(url):
    result = common.fetchPage({"link": url})

    if result["status"] != 200:
        dialogErrorResult("Unable to connect to Netflix")
        return False

    if not 'id="page-MyList"' in result['content']:
        if 'id="page-LOGIN"' in result['content']:
            if not login():
                return False
            return listMyVideos(url)

        if 'id="page-ProfilesGate"' in result['content']:
            if not chooseProfile(result['content']):
                return False
            return listMyVideos(url)

        dialogErrorResult(result, "Unexpected content on myList page")
        return False

    xbmcplugin.setContent(pluginhandle, "movies")

    gallery = common.parseDOM(result['content'], "div", attrs = {'class': 'agMovie agMovie-lulg'})

    for item in gallery:
        poster = common.parseDOM(item, "img", ret = 'src')[0]
        name = common.parseDOM(item, "img", ret = 'alt')[0]
        playLink = common.parseDOM(item, "a", ret = 'href')[0]
        videoId = common.parseDOM(item, "a", ret = 'id')[0][2:-2]
        #videoInfo = getVideoInfo(videoId, name, poster, playLink)

        addDir(name, rewritePlayLink(playLink, "movie"), "playVideo", poster)

    xbmcplugin.endOfDirectory(pluginhandle)
    return True


def playVideo(url):
    xbmc.Player().stop()
    xbmc.executebuiltin('XBMC.StartAndroidActivity("com.netflix.mediaclient", "android.intent.action.VIEW", "", "' + url + '")')


# Helpers

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
        fh = common.openFile(profileFile, u'wb')
        fh.write(common.makeAscii(token))
        fh.close()
        cookiejar.save(cookieFile)
        return True

    dialogError("Error", "No profiles found")
    return False


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


def addDir(name, url, action, iconimage):
    u = sys.argv[0]+"?url="+urllib.quote_plus(url)+"&action="+str(action)+"&thumb="+str(iconimage)
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


def deleteCookies():
    if os.path.exists(cookieFile):
        os.remove(cookieFile)


def deleteCache():
    if os.path.exists(cacheFolder):
        try:
            shutil.rmtree(cacheFolder)
        except:
            shutil.rmtree(cacheFolder)


def getParameters(parameterString):
    common.log("", 5)
    commands = {}
    splitCommands = parameterString[parameterString.find('?') + 1:].split('&')

    for command in splitCommands:
        if (len(command) > 0):
            splitCommand = command.split('=')
            key = splitCommand[0]
            try:
                value = urllib.unquote_plus(splitCommand[1])
            except Exception:
                value = ""

            commands[key] = value

    common.log(repr(commands), 5)
    return commands


def getVideoInfo(videoId, name, poster, playLink):
    cacheFile = os.path.join(cacheFolder, videoID+".cache")
    if os.path.exists(cacheFile):
        fh = common.openFile(cacheFile, 'r')
        content = json.load(fh)
        fh.close()
        return content

    trkid = getParameters(playLink)['trkid']
    result = common.fetchPage({
             "link": webMovies + "?ibob=true&authURL=" + authUrl + "&movieid=" + videoId + "&trkid=" + trkid,
             "header": [["X-Requested-With", "XMLHttpRequest"]]
             })

    if result["status"] != 200:
        dialogErrorResult("Unable to connect to Netflix")
        return False

    content = result['content']
    fh = open(cacheFile, 'w')
    fh.write(content)
    fh.close()

    return content


def rewritePlayLink(url, videoType):
    params = getParameters(url)
    
    if videoType == 'movie':
        videoPath = nflxPathMovies
    elif videoType == 'tv':
        videoPath = nflxPathShows
    else:
        xbmc.executebuiltin('XBMC.Notification("Error:","Unknown video type",5000)')
        return ""
    
    query = "action=" + nflxActionPlay + "&" + nflxParamMovieId + "=" + videoPath + params['movieid'] + "&" + nflxParamTargetId + "=" + params['tctx']
    
    return nflxPath + urllib.quote_plus(query)



# no more methods

params = getParameters(sys.argv[2])
action = params.get('action', '')

common.log(sys.argv[2])
common.log(json.dumps(params))

if action == 'listMyVideos':
    listMyVideos(params['url'])
elif action == 'playVideo':
    playVideo(params['url'])
else:
    index()

