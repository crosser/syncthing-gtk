#!/usr/bin/env python2
"""
Nautilus plugin for Syncthing.
This program is part of Syncthing-GTK, but can be used independently
with small modification
"""

from gi.repository import Nautilus, GObject, Gio, GLib
from syncthing_gtk.tools import init_logging, set_logging_level
from syncthing_gtk import Daemon
import os, sys, logging
log = logging.getLogger("NautilusPlugin")

# Output options
VERBOSE	= True
DEBUG	= True

# Magic numbers
STATE_IDLE		= 0
STATE_SYNCING	= 1
STATE_OFFLINE	= 2
STATE_STOPPED	= 3

class STGTKExtension_Nautilus(GObject.GObject, Nautilus.InfoProvider):
	def __init__(self):
		# Prepare stuff
		init_logging()
		set_logging_level(VERBOSE, DEBUG)
		log.info("Initializing...")
		# ready field is set to True while connection to Syncthing
		# daemon is maintained.
		self.ready = False
		try:
			self.daemon = Daemon()
		except Exception, e:
			# Syncthing is not configured, most likely never launched.
			log.error("%s", e)
			log.error("Failed to read Syncthing configuration.")
			return
		# List of known repos + their states
		self.folders = {}
		self.rid_to_path = {}
		# List (cache) for folders that are known to be placed bellow
		# some syncthing repo
		self.subfolders = set([])
		# List (cache) for files with emblems
		self.files = set([])
		# Connect to Daemon object signals
		self.daemon.connect("connected", self.cb_connected)
		self.daemon.connect("connection-error", self.cb_syncthing_con_error)
		self.daemon.connect("disconnected", self.cb_syncthing_disconnected)
		self.daemon.connect("folder-added", self.cb_syncthing_folder_added)
		self.daemon.connect("folder-sync-started", self.cb_syncthing_folder_state_changed, STATE_SYNCING)
		self.daemon.connect("folder-sync-finished", self.cb_syncthing_folder_state_changed, STATE_IDLE)
		self.daemon.connect("folder-stopped", self.cb_syncthing_folder_state_changed, STATE_STOPPED)
		
		log.info("Initialized.")
		# Let Daemon object connect to Syncthing
		self.daemon.reconnect()
	
	### Internal stuff
	def _clear_emblems(self):
		""" Clear emblems on all files that had emblem added """
		for path in self.files:
			file = Nautilus.FileInfo.create(Gio.File.new_for_path(path))
			print "cleared emblem on ", path
			# invalidate_extension_info will force nautilus to re-read emblems
			file.invalidate_extension_info()
		self.files = set([])
	
	### Daemon callbacks
	def cb_connected(self, *a):
		"""
		Called when connection to Syncthing daemon is created.
		Clears list of known folders and all caches.
		Also asks Nautilus to clear all emblems.
		"""
		self.folders = {}
		self.subfolders = set([])
		self._clear_emblems()
		self.ready = True
		log.info("Connected to Syncthing daemon")
	
	def cb_syncthing_folder_added(self, daemon, rid, r):
		"""
		Called when folder is readed from configuration (by syncthing
		daemon, not locally).
		Adds path to list of known repositories and asks Nautilus to
		re-read emblem.
		"""
		path = os.path.expanduser(r["Path"])
		self.rid_to_path[rid] = path
		self.folders[path] = STATE_OFFLINE
		file = Nautilus.FileInfo.create(Gio.File.new_for_path(path))
		file.invalidate_extension_info()
	
	def cb_syncthing_con_error(self, *a):
		# log.info("con-error")
		# self.daemon.reconnect()
		pass
	
	def cb_syncthing_disconnected(self, *a):
		"""
		Called when connection to Syncthing daemon is lost or Daemon
		object fails to (re)connect.
		Check if connection was already finished before and clears up
		stuff in that case.
		"""
		if self.ready:
			log.info("Connection to Syncthing daemon lost")
			self.ready = False
			self._clear_emblems()
		self.daemon.reconnect()
	
	
	def cb_syncthing_folder_state_changed(self, daemon, rid, state):
		if rid in self.rid_to_path:
			path = self.rid_to_path[rid]
			self.folders[path] = state
			log.debug("State of %s changed to %s", path, state)
			file = Nautilus.FileInfo.create(Gio.File.new_for_path(path))
			file.invalidate_extension_info()
	
	### Plugin stuff
	def update_file_info(self, file):
		if not self.ready: return
		# Check if folder is one of repositories managed by syncthing
		path = file.get_location().get_path()
		if path in self.folders:
			# Determine what emblem should be used
			state = self.folders[path]
			if state == STATE_IDLE:
				# File manager probably shoudn't care about folder being scanned
				file.add_emblem("syncthing")
			elif state == STATE_STOPPED:
				file.add_emblem("syncthing-error")
			elif state == STATE_SYNCING:
				file.add_emblem("syncthing-active")
			else:
				# Default (i-have-no-idea-what-happened) state
				file.add_emblem("syncthing-offline")
			self.files.add(path)
