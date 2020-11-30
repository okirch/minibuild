#
# Build job running on the local machine w/o containers or anything
# involved.
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

class LocalCompute(brcoti_core.Compute):
	def __init__(self, global_config, config):
		super(LocalCompute, self).__init__(global_config, config)

	def spawn(self, flavor):
		return LocalComputeNode(self)

class LocalFile(brcoti_core.ComputeResourceFile):
	def __init__(self, path):
		super(LocalFile, self).__init__(path)

	def open(self, mode = 'r'):
		return open(self.path, mode)

	def hostpath(self):
		return self.path

class LocalDirectory(brcoti_core.ComputeResourceDirectory):
	def __init__(self, path):
		if not path.startswith('/'):
			path = os.path.join(os.getcwd(), path)
		super(LocalDirectory, self).__init__(path)

	def _realpath(self, path):
		if path.startswith('/'):
			return path
		return os.path.join(self.path, path)

	def glob_files(self, path_pattern):
		path_pattern = self._realpath(path_pattern)

		result = []
		for name in glob.glob(path_pattern):
			fh = self.lookup(name)
			if not fh:
				raise ValueError("glob returns \"%s\" which does not seem to be a valid (relative) path" % (name))
			result.append(fh)
		return result
		# return [self.lookup(path) for path in glob.glob(path_pattern)]

	def lookup(self, path):
		path = self._realpath(path)
		if not os.path.exists(path):
			return None
		if os.path.isdir(path):
			return LocalDirectory(path)
		return LocalFile(path)

	def open(self, path, mode = 'r'):
		path = self._realpath(path)
		return open(path, mode)

	def hostpath(self):
		return self.path

class LocalComputeNode(brcoti_core.ComputeNode):
	def __init__(self, backend):
		super(LocalComputeNode, self).__init__(backend)

	def putenv(self, name, value):
		os.putenv(name, value)

	def _perform_command(self, f, cmd, working_dir):
		if working_dir is None:
			exit_code = f(cmd)
		else:
			if isinstance(working_dir, brcoti_core.ComputeResourceDirectory):
				working_dir = working_dir.path
			cwd = os.getcwd()
			try:
				os.chdir(working_dir)
				exit_code = f(cmd)
			finally:
				os.chdir(cwd)

		return exit_code

	def _run_command(self, cmd, working_dir = None, privileged_user = False):
		# ignore privileged_user argument; for now we just run everything
		# as the invoking user anyway
		return self._perform_command(os.system, cmd, working_dir)

	def _popen(self, cmd, mode = 'r', working_dir = None):
		return self._perform_command(lambda cmd: os.popen(cmd, mode), cmd, working_dir)

	def get_directory(self, path):
		if not os.path.isdir(path):
			raise ValueError("%s is not a directory" % (path))
		return LocalDirectory(path)

	def shutdown(self):
		pass

def compute_factory(global_config, config):
        return LocalCompute(global_config, config)

