#
# Build job running inside a container.
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

import os
import sys
import brcoti_core
import glob

class PodmanCompute(brcoti_core.Compute):
	def __init__(self, opts):
		pass

	def spawn(self, flavor):
		return PodmanComputeNode(flavor)

class PodmanPathMixin:
	def __init__(self, root):
		self.root = root

	def __repr__(self):
		return "container:" + self.path

	def _realpath(self, path):
		if path is None:
			path = self.path
		if not path.startswith('/'):
			path = os.path.join(self.path, path)
		return path

	def _hostpath(self, path):
		return self.root + self._realpath(path)

	def hostpath(self):
		return self.root + self.path

class PodmanFile(PodmanPathMixin, brcoti_core.ComputeResourceFile):
	def __init__(self, root, path):
		PodmanPathMixin.__init__(self, root)

		assert(path.startswith('/'))
		brcoti_core.ComputeResourceFile.__init__(self, path)

	def open(self, mode = 'r'):
		path = self.hostpath()
		return open(path, mode)

class PodmanDirectory(PodmanPathMixin, brcoti_core.ComputeResourceDirectory):
	def __init__(self, root, path):
		PodmanPathMixin.__init__(self, root)

		assert(path.startswith('/'))
		brcoti_core.ComputeResourceDirectory.__init__(self, path)

	def glob_files(self, path_pattern):
		result = []

		path_pattern = self._hostpath(path_pattern)
		for name in glob.glob(path_pattern):
			assert(name.startswith(self.root))
			try:
				name = name.removeprefix(self.root)
			except:
				name = name[len(self.root):]

			fh = self.lookup(name)
			if not fh:
				raise ValueError("glob returns \"%s\" which does not seem to be a valid (relative) path" % (name))
			result.append(fh)
		return result

	def lookup(self, path):
		path = self._realpath(path)

		hp = self._hostpath(path)
		if not os.path.exists(hp):
			return None
		if os.path.isdir(hp):
			return PodmanDirectory(self.root, path)
		return PodmanFile(self.root, path)

	def open(self, path, mode = 'r'):
		path = self._realpath(path)
		path = self._hostpath(path)
		return open(path, mode)

class PodmanComputeNode(brcoti_core.ComputeNode):
	def __init__(self, flavor):
		super(PodmanComputeNode, self).__init__()

		self.container_id = None
		self.container_root = None

		# Kludge to make https://localhost URLs work in the container
		self._mapped_hostname = None

		self.start(flavor)

		self.env = {}

		print("Created container %s; root=%s" % (self.container_id, self.container_root))

	def __del__(self):
		if not self.cleanup_on_exit:
			return

		if self.container_root:
			brcoti_core.run_command("podman umount %s" % self.container_id)
		if self.container_id:
			brcoti_core.run_command("podman stop %s" % self.container_id)

	def start(self, flavor):
		assert(self.container_id is None)

		self.setup_localhost_mapping()

		exec = "podman run --rm -d"
		for host in self.hosts:
			exec += " --add-host %s" % host
		exec += " brcoti-%s" % flavor

		f = brcoti_core.popen(exec)

		self.container_id = f.read().strip()
		assert(self.container_id)

		f = brcoti_core.popen("podman mount %s" % self.container_id)
		self.container_root = f.read().strip()
		assert(self.container_root)

	def default_build_dir(self):
		return "/usr/src/packages/BUILD"

	def translate_url(self, url):
		import urllib.parse
		import socket

		parsed_url = urllib.parse.urlparse(url)
		if parsed_url.hostname != 'localhost':
			return url

		self._mapped_hostname = socket.getfqdn()

		if parsed_url.port:
			netloc = "%s:%s" % (self._mapped_hostname, parsed_url.port)
		else:
			netloc = self._mapped_hostname

		parsed_url = parsed_url._replace(netloc = netloc)
		result = urllib.parse.urlunparse(parsed_url)

		print("translated url \"%s\" -> \"%s\"" % (url, result))
		return result

	def trusted_hosts(self):
		if self._mapped_hostname:
			return [self._mapped_hostname]
		return []

	def setup_localhost_mapping(self):
		self.hosts = []

	def putenv(self, name, value):
		self.env[name] = value

	def _run_command(self, cmd, working_dir = None):
		exec = "podman exec"
		if working_dir:
			if isinstance(working_dir, brcoti_core.ComputeResourceFS):
				working_dir = working_dir.path
			exec += " --workdir \'%s\'" % working_dir

		for name, value in self.env.items():
			exec += " --env %s='%s'" % (name, value)

		# FIXME: make this configurable
		exec += " --user build:build"
		exec += " %s %s" % (self.container_id, cmd)

		print(exec)
		sys.stdout.flush()

		return os.system(exec)

	def _popen(self, cmd, mode = 'r'):
		return os.popen(cmd, mode)

	def get_directory(self, path):
		assert(path.startswith('/'))

		if not os.path.isdir(self.container_root + path):
			raise ValueError("%s is not a directory (inside the container)" % (path))
		return PodmanDirectory(self.container_root, path)

	def shutdown(self):
		pass

def compute_factory(opts):
        return PodmanCompute(opts)


