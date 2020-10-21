#!/usr/bin/python3
#
# This is a simplistic build script for building artefacts of various
# programming languages natively (eg using pip, npm etc) and upload the
# resulting artefacts to a local repo.
#
#   Copyright (C) 2020 Olaf Kirch <okir@suse.de>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#

import sys
import os
import os.path
import io
import glob
import shutil

def run_command(cmd, ignore_exitcode = False):
	print("Running %s" % cmd)

	# Avoid messing up the order of our output and the output of subprocesses when
	# stdout is redirected
	sys.stdout.flush()
	sys.stderr.flush()
	if os.system(cmd) != 0 and not ignore_exitcode:
		raise ValueError("Command `%s' returned non-zero exit status" % cmd)

class Object(object):
	def mni(self):
		import sys
		import traceback
		import threading

		my_thread = threading.current_thread()
		for thread, frame in sys._current_frames().items():
			if thread != my_thread.ident:
				continue

			if frame.f_code.co_name != 'mni':
				break

			frame = frame.f_back
			raise NotImplementedError("%s.%s(): method not implemented" % (self.__class__.__name__, frame.f_code.co_name))

		# we were trying to be too clever; or something changed in the way python handles stack frames.
		# Fall back to a more bland error message
		raise NotImplementedError("%s: method not implemented" % (self.__class__.__name__))

class PackageBuildInfo(Object):
	def __init__(self, name, version = None):
		self.name = name
		self.version = version

		self.url = None
		self.local_path = None

	def id(self):
		self.nmi()

	def git_url(self):
		self.nmi()

	@property
	def is_source(self):
		self.nmi()

class PackageReleaseInfo(Object):
	def __init__(self, name, version):
		self.name = name
		self.version = version

		self.builds = []

	def id(self):
		self.nmi()

	def more_recent_than(self, other):
		self.nmi()

	def add_build(self, build):
		self.builds.append(build)

class PackageInfo(Object):
	def __init__(self, name):
		self.name = name
		self.releases = []

	def add_release(self, release):
		self.releases.append(release)

	def versions(self):
		return [r.version for r in self.releases]

class DownloadFinder(Object):
	def __init__(self, verbose):
		self.verbose = verbose

	def get_best_match(self, index):
		self.mni()

class PackageIndex(Object):
	def get_package_info(self, name):
		self.mni()

class HTTPPackageIndex(PackageIndex):
	def __init__(self, url):
		self.url = url
		self._pkg_url_template = None

	def get_package_info(self, name):
		import urllib.request

		url = self._pkg_url_template.format(index_url = self.url, pkg_name = name)

		resp = urllib.request.urlopen(url)
		if resp.status != 200:
			raise ValueError("Unable to get package info for %s: HTTP response %s (%s)" % (
					name, resp.status, resp.reason))

		return self.process_package_info(name, resp)

	# returns a PackageInfo object
	def process_package_info(self, name, http_resp):
		self.mni()

# For now, this is a very trivial downloader.
# This could be something much more complex that uses caches, OBS, yadda yadda
class Downloader(object):
	def __init__(self):
		pass

	def download(self, build, destdir = None):
		import urllib.request

		if build.local_path:
			return build.local_path

		assert(build.url)
		assert(build.filename)

		url = build.url
		resp = urllib.request.urlopen(url)
		if resp.status != 200:
			raise ValueError("Unable to download %s from %s (HTTP status %s %s)" % (
					build.filename, url, resp.status, resp.reason))

		filename = build.filename
		if destdir:
			filename = os.path.join(destdir, filename)

		with open(filename, "wb") as f:
			f.write(resp.read())

		print("Downloaded %s from %s" % (filename, url))

		build.local_path = filename
		return filename

# For now, a very trivial uploader.
class Uploader(Object):
	def __init__(self):
		pass

	def describe(self):
		self.mni()

	def upload(self, build):
		self.mni()

class BuildDirectory(Object):
	def __init__(self, build_dir):
		self.unpacked_dir = build_dir

	@property
	def location(self):
		return self.unpacked_dir

	def build(self, quiet = False):
		self.mni()

	def unchanged_from_previous_build(self, build_state):
		self.mni()

	def guess_build_dependencies(self):
		self.mni()

	def finalize_build_depdendencies(self, downloader):
		self.mni()

	def prepare_results(self, build_state):
		self.mni()

	def build_requires_as_string(self):
		self.mni()

class BuildState(Object):
	def __init__(self, savedir):
		import tempfile

		self.savedir = savedir
		self.tmpdir = tempfile.TemporaryDirectory(prefix = "brcoti-")

	def __del__(self):
		self.cleanup()

	def exists(self):
		return os.path.exists(self.savedir)

	def rebuild_required(self):
		self.mni()

	def commit(self):
		if not self.tmpdir:
			print("%s: changes already committed" % self.savedir)
			return

		# Clean up the savedir
		if os.path.exists(self.savedir):
			shutil.rmtree(self.savedir)
		os.makedirs(self.savedir, mode = 0o755)

		# And copy our data over it
		print("Committing build state to %s:" % self.savedir, end = ' ')
		for file in glob.glob(os.path.join(self.tmpdir.name, "*")):
			print(os.path.basename(file), end = ' ')
			shutil.copy(file, self.savedir)
		print("")

	def cleanup(self):
		if self.tmpdir:
			del self.tmpdir
		self.tmpdir = None

	def get_old_path(self, name):
		return os.path.join(self.savedir, name)

	def get_new_path(self, name):
		return os.path.join(self.tmpdir.name, name)

	def maybe_save_file(self, src, dst = None):
		if not os.path.exists(src):
			print("Not saving %s (does not exist)" % src)
			return None

		return self.save_file(src, dst)

	def save_file(self, src):
		dst = self.tmpdir.name

		print("Saving %s to %s" % (src, dst))
		shutil.copy(src, dst)

		if os.path.isdir(dst):
			return os.path.join(dst, os.path.basename(src))
		return dst

	def write_file(self, name, data, desc = None):
		path = os.path.join(self.tmpdir.name, name)

		if desc:
			print("Writing %s to %s" % (desc, path))
		else:
			print("Writing %s" % path)
		with open(path, "w") as f:
			f.write(data)

class Engine(Object):
	def __init__(self, name):
		self.name = name

		self.downloader = None
		self.uploader = None

	def downloader(self):
		return Downloader()

	def uploader(self):
		self.mni()

	def build_info_from_local_file(self, path):
		self.mni()

	def build_source_locate(self, req_string, verbose = True):
		self.mni()

	def build_state_factory(self, sdist):
		self.mni()

	def build_unpack(self, sdist):
		self.mni()

	@staticmethod
	def factory(name, opts):
		if name == 'python':
			import brcoti_python

			return brcoti_python.engine_factory(opts)
