#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
michel-orgmode -- a script to push/pull an org-mode text file to/from a google
                  tasks list.

"""

import httplib2

from apiclient import discovery
import oauth2client
from oauth2client import client
from oauth2client import tools

from difflib import SequenceMatcher
import codecs
import argparse
import os.path
import shutil
import sys
import re
import io
import ipdb

RATIO_THRESHOLD = 0.85
headline_regex = re.compile("^(\*+) *(DONE|TODO)? *(.*)")
spec_re = re.compile("([^.]+): (.+)")

class TasksTree(object):
    """
    Tree for holding tasks

    A TasksTree:
    - is a task (except the root, which just holds the list)
    - has subtasks
    - may have a task_id
    - may have a title
    """

    def __init__(self, title=None, task_id=None, task_notes=None, task_todo=False, task_completed=False):
        self.title = title
        self.task_id = task_id
        self.subtasks = []
        self.notes = task_notes or []
        self.todo = task_todo
        self.completed = task_completed
        
    def __getitem__(self, key):
        return self.subtasks[key]
         
    def __setitem__(self, key, val):
        self.subtasks[key] = val
        
    def __delitem__(self, key):
        del(self.subtasks[key])

    def __len__(self):
        return len(self.subtasks)

    def get_task_with_id(self, task_id):
        """Returns the task of given id"""
        if self.task_id == task_id:
            return self
        else:
            # depth first search for id
            for subtask in self.subtasks:
                if subtask.get_task_with_id(task_id) is not None:
                    return subtask.get_task_with_id(task_id)
            # if there are no subtasks to search
            return None

    def add_subtask(self, title, task_id = None, parent_id = None,
                    task_notes = None, task_todo = False, task_completed = False):
        """
        Adds a subtask to the tree
        - with the specified task_id
        - as a child of parent_id
        """
        if parent_id is None:
            task = TasksTree(title, task_id, task_notes, task_todo, task_completed)
            self.subtasks.append(task)
            return task
        else:
            if self.get_task_with_id(parent_id) is None:
                raise ValueError("No element with suitable parent id")
            
            return self.get_task_with_id(parent_id).add_subtask(title, task_id, None,
                                                         task_notes, task_todo, task_completed)

    def add_subtree(self, tree_to_add, include_root=False, root_title=None,
            root_notes=None):
        """Add *tree_to_add* as a subtree of this tree.
        
        If *include_root* is False, then the children of *tree_to_add* will be
        added as children of this tree's root node.  Otherwise, the root node
        of *tree_to_add* will be added as a child of this tree's root node.
        
        The *root_title* and *root_notes* arguments are optional, and can be
        used to set the title and notes of *tree_to_add*'s root node when
        *include_root* is True. 
        
        """
        if not include_root:
            self.subtasks.extend(tree_to_add.subtasks)
        else:
            if root_title is not None:
                tree_to_add.title = root_title
            if tree_to_add.title is None:
                tree_to_add.title = ""
                
            if root_notes is not None:
                tree_to_add.notes = root_notes
            
            self.subtasks.append(tree_to_add)

    def last_task_node_at_level(self, level):
        """Return the last task added at a given level of the tree.
        
        Level 0 is the "root" node of the tree, and there is only one node at
        this level, which contains all of the level 1 nodes (tasks/headlines).
        
        A TaskTree object is returned that corresponds to the last task having
        the specified level.  This TaskTree object will have the last task as
        the root node of the tree, and will maintain all of the node's
        descendants.
        
        """
        if level == 0:
            return self
        else:
            res = None
            for subtask in self.subtasks:
                x = subtask.last_task_node_at_level(level - 1)
                if x is not None:
                    res = x
            if res is not None:
                return res

    def push(self, service, list_id, parent = None, root=True):
        """Pushes the task tree to the given list"""
        # We do not want to push the root node
        if not root:
            insert_cmd_args = {
                'tasklist': list_id,
                'body': {
                    'title': self.title,
                    'notes': '\n'.join(self.notes),
                    'status': 'completed' if self.completed else 'needsAction'
                }
            }
            if parent:
                insert_cmd_args['parent'] = parent
            res = service.tasks().insert(**insert_cmd_args).execute()
            self.task_id = res['id']
        # the API head inserts, so we insert in reverse.
        for subtask in reversed(self.subtasks):
            subtask.push(service, list_id, parent=self.task_id, root=False)

    def _lines(self, level):
        """Returns the sequence of lines of the string representation"""
        res = []
        
        for subtask in self.subtasks:
            line = '*' * (level + 1) + ' '
            if subtask.completed:
                line += 'DONE '
            elif subtask.todo:
                line += 'TODO '
            line += subtask.title
                
            res.append(line)

            for note_line in subtask.notes:
                # add initial space to lines starting w/'*', so that it isn't treated as a task
                if note_line.startswith("*"):
                    note_line = " " + note_line
                note_line = ' ' * (level + 2) + note_line
                res.append(note_line)
                
            res += subtask._lines(level + 1)
            
        return res


    def __str__(self):
        """string representation of the tree.
        
        Only the root-node's children (and their descendents...) are printed,
        not the root-node itself.
        
        """
        # always add a trailing "\n" because text-files normally include a "\n"
        # at the end of the last line of the file.
        return '\n'.join(self._lines(0)) + "\n"

    def _print(self):
        print(self.__str__())

    def write_to_orgfile(self, fname):
        f = codecs.open(fname, "w", "utf-8")
        f.write(self.__str__())
        f.close()

def save_data_path(file_name):
    data_path = os.path.join(os.path.expanduser('~'), ".michel")
    if not os.path.exists(data_path):
        os.makedirs(data_path)
    return os.path.join(data_path, file_name)
    
def concatenate_trees(t1, t2):
    """Combine tree *t1*'s children with tree *t2*'s children.
    
    A tree is returned whose children include the children of *t1* and the
    children of *t2*.  The root node of the returned tree is a dummy node
    having no title.
    
    Note: children are treated as references, so modifying *t1* after creating
    the combined tree will also modify the combined tree.
    
    """
    joined_tree = TasksTree()
    joined_tree.add_subtree(t1)
    joined_tree.add_subtree(t2)

    return joined_tree
    
def treemerge(tree_org, tree_remote):
    tasks_org = []
    tasks_remote = []

    disassemble_tree(tree_org, tasks_org)
    disassemble_tree(tree_remote, tasks_remote)

    tasks_org.sort(key=lambda node: node.hash_sum)
    tasks_remote.sort(key=lambda node: node.hash_sum)

    mapping = []

    # first step, exact matching
    index_remote, index_org = 0, 0
    while index_remote < len(tasks_remote):
        is_mapped = False
        index_org = 0
        
        while index_org < len(tasks_org):
            if tasks_remote[index_remote].is_equal(tasks_org[index_org]):
                mapping.append(tuple([tasks_remote.pop(index_remote), tasks_org.pop(index_org), True]))
                is_mapped = True
                break
            else:
                index_org += 1

        if not is_mapped:
            index_remote += 1

    # second step, fuzzy matching
    index_remote, index_org = 0, 0
    while index_remote < len(tasks_remote):
        index_org = 0
        best_index_org = None
        best_ratio = RATIO_THRESHOLD
        
        while index_org < len(tasks_org):
            ratio = tasks_org[index_org].calc_ratio(tasks_remote[index_remote])
            if ratio > best_ratio:
                best_ratio = ratio
                best_index_org = index_org
            index_org += 1

        if best_index_org is not None:
            mapping.append(tuple([tasks_remote.pop(index_remote), tasks_org.pop(best_index_org), False]))
        else:
            index_remote += 1

    # third step, patching org tree
    for map_entry in mapping:
        diff_notes = []

        # Merge attributes
        if map_entry[0].task.todo == True and map_entry[1].task.todo != True:
            map_entry[1].task.todo = True
        if map_entry[0].task.completed == True and map_entry[1].task.completed != True:
            map_entry[1].task.completed = True

        # Merge contents
        if map_entry[0].task.title != map_entry[1].task.title:
            if map_entry[1].task.title not in map_entry[0].titles:
                diff_notes.append("PREV_ORG_TITLE: {0}".format(map_entry[1].task.title))
                map_entry[1].task.title = map_entry[0].task.title

        if map_entry[0].task.notes != map_entry[1].task.notes:
            for note_line in map_entry[0].task.notes:
                matches = spec_re.findall(note_line)
                if len(matches) > 0:
                    if matches[0][0] == "PREV_ORG_TITLE":
                        continue
                    elif matches[0][0] == "REMOTE_APPEND_NOTE":
                        note_line = matches[0][1]
                    
                if note_line not in map_entry[1].task.notes:
                    diff_notes.append("REMOTE_APPEND_NOTE: {0}".format(note_line))

        map_entry[1].task.notes += diff_notes

    # fourth step, append new items
    for i in range(len(tasks_remote)):
        new_task = tasks_remote[i]

        try:
            parent_task = next(x for x in mapping if x[0] == new_task.parent)[1].task
        except StopIteration:
            parent_task = tree_org
            new_task.task.notes.append("MERGE_INFO: parent is not exist")

        created_task = parent_task.add_subtask(
            title=new_task.task.title,
            task_notes=new_task.task.notes,
            task_todo=new_task.task.todo,
            task_completed=new_task.task.completed)

        mapping.append(tuple([PartTree(parent_task, created_task), new_task, True]))

class PartTree:
    def __init__(self, parent, task):
        self.task = task
        self.parent = parent
        self.hash_sum = 0
        self.titles = []

        if task.title is not None:
            self.titles.append(task.title)
        
        notes = []
        for note_line in task.notes:
            matches = spec_re.findall(note_line)
            if len(matches) > 0:
                if matches[0][0] == "PREV_ORG_TITLE":
                    if matches[0][1] not in self.titles:
                        self.titles.append(matches[0][1])
                    continue
                elif matches[0][0] == "REMOTE_APPEND_NOTE":
                    note_line = matches[0][1]
            notes.append(note_line)
        self.notes = " ".join(notes)

        for title in self.titles:
            for char in title:
                self.hash_sum += ord(char)
        for char in self.notes:
            self.hash_sum += ord(char)

    def is_equal(self, another):
        if len(self.titles) == 0 and len(another.titles) == 0:
            return True
        
        return any(a == b for a in self.titles for b in another.titles) and self.notes == another.notes

    def calc_ratio(self, another):
        return max(self.__calc_ratio(a, b) for a in self.titles for b in another.titles) * 0.7 +\
            self.__calc_ratio(self.notes, another.notes) * 0.3

    def __calc_ratio(self, str1, str2):
        if len(str1) == 0 and len(str2) == 0:
            return 1
        
        seq = SequenceMatcher(None, str1, str2)
        ratio = 0
        
        for opcode in seq.get_opcodes():
            if opcode[0] == 'equal' or opcode[0] == 'insert':
                continue
            if opcode[0] == 'delete':
                ratio += opcode[2] - opcode[1]
            if opcode[0] == 'replace':
                ratio += max(opcode[4] - opcode[3], opcode[2] - opcode[1])
        return 1 - ratio/max(len(str1), len(str2))

    def __str__(self):
        return "{0} {1}, p: {2}".format(self.task.title, self.hash_sum, self.parent)

    def __repr__(self):
        return str(self)

def disassemble_tree(tree, disassemblies, parent = None):
    current = PartTree(parent, tree)
    disassemblies.append(current)

    for i in range(len(tree)):
        disassemble_tree(tree[i], disassemblies, current)
        

def get_service(profile_name):
    """
    Handle oauth's shit (copy-pasta from
    http://code.google.com/apis/tasks/v1/using.html)
    Yes I do publish a secret key here, apparently it is normal
    http://stackoverflow.com/questions/7274554/why-google-native-oauth2-flow-require-client-secret
    """
    storage = oauth2client.file.Storage(save_data_path("oauth.dat"))
    credentials = storage.get()
    if not credentials or credentials.invalid:
        flow = client.OAuth2WebServerFlow(
            client_id='617841371351.apps.googleusercontent.com',
            client_secret='_HVmphe0rqwxqSR8523M6g_g',
            scope='https://www.googleapis.com/auth/tasks',
            user_agent='michel/0.0.1')
        flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args("")
        credentials = tools.run_flow(flow, storage, flags)
    http = httplib2.Http()
    http = credentials.authorize(http)
    return discovery.build(serviceName='tasks', version='v1', http=http)

def get_list_id(service, list_name=None):
    if list_name is None:
        list_id = "@default"
    else:
        # look up id by list name
        tasklists = service.tasklists().list().execute()
        for tasklist in tasklists['items']:
            if tasklist['title'] == list_name:
                list_id = tasklist['id']
                break
        else:
            # no list with the given name was found
            print('\nERROR: No google task-list named "%s"\n' % list_name)
            sys.exit(2)

    return list_id

def get_gtask_list_as_tasktree(profile, list_name=None):
    """Get a TaskTree object representing a google tasks list.
    
    The Google Tasks list named *list_name* is retrieved, and converted into a
    TaskTree object which is returned.  If *list_name* is not specified, then
    the default Google-Tasks list will be used.
    
    """
    service = get_service(profile)
    list_id = get_list_id(service, list_name)
    tasks = service.tasks().list(tasklist=list_id).execute()
    tasklist = [t for t in tasks.get('items', [])]

    return tasklist_to_tasktree(tasklist)

def tasklist_to_tasktree(tasklist):
    """Convert a list of task dictionaries to a task-tree.

    Take a list of task-dictionaries, and convert them to a task-tree object.
    Each dictionary can have the following keys:

        title -- title of task [required]
        id -- unique identification number of task [required]
        parent -- unique identification number of task's parent
        notes -- additional text describing task
        status -- flag indicating whether or not task is crossed off

    """
    tasks_tree = TasksTree()

    fail_count = 0
    while tasklist != [] and fail_count < 1000:
        t = tasklist.pop(0)
        try:
            tasks_tree.add_subtask(
                title = t['title'],
                task_id = t['id'],
                parent_id = t.get('parent'),
                task_notes = t.get('notes').split('\n') if t.get('notes') else None,
                task_todo = True,
                task_completed = t.get('status') == 'completed')
        except ValueError:
            fail_count += 1
            tasklist.append(t)
 
    return tasks_tree

def print_todolist(profile, list_name=None):
    """Print an orgmode-formatted string representing a google tasks list.
    
    The Google Tasks list named *list_name* is used.  If *list_name* is not
    specified, then the default Google-Tasks list will be used.
    
    """
    tasks_tree = get_gtask_list_as_tasktree(profile, list_name)
    tasks_tree._print()

def write_todolist(orgfile_path, profile, list_name=None):
    """Create an orgmode-formatted file representing a google tasks list.
    
    The Google Tasks list named *list_name* is used.  If *list_name* is not
    specified, then the default Google-Tasks list will be used.
    
    """
    tasks_tree = get_gtask_list_as_tasktree(profile, list_name)
    tasks_tree.write_to_orgfile(orgfile_path)

def erase_todolist(profile, list_id):
    """Erases the todo list of given id"""
    service = get_service(profile)
    tasks = service.tasks().list(tasklist=list_id).execute()
    for task in tasks.get('items', []):
        service.tasks().delete(tasklist=list_id,
                task=task['id']).execute()


def parse_path(path):
    """Parses an org-mode file and returns a tree"""
    file_lines = codecs.open(path, "r", "utf-8").readlines()
    file_text = "".join(file_lines)
    return parse_text_to_tree(file_text)
    
def parse_text_to_tree(text):
    """Parses an org-mode formatted block of text and returns a tree"""
    # create a (read-only) file object containing *text*
    f = io.StringIO(text)
    
    tasks_tree = TasksTree()
    last_task = None

    for line in f:
        matches = headline_regex.findall(line.rstrip("\n"))
        try:
            # assign task_depth; root depth starts at 0
            indent_level = len(matches[0][0])
            
            # if we get to this point, then it means that a new task is
            # starting on this line -- we need to add the last-parsed task
            # to the tree (if this isn't the first task encountered)
            
            # add the task to the tree
            last_task = tasks_tree.last_task_node_at_level(indent_level-1).add_subtask(
                title=matches[0][2],
                task_todo=matches[0][1] == 'DONE' or matches[0][1] == 'TODO',
                task_completed=matches[0][1] == 'DONE')

        except IndexError:
            # this is not a task, but a task-notes line
            last_task.notes.append(line.strip())

    f.close()
    return tasks_tree

def push_todolist(path, profile, list_name):
    """Pushes the specified file to the specified todolist"""
    service = get_service(profile)
    list_id = get_list_id(service, list_name)
    tasks_tree = parse_path(path)
    erase_todolist(profile, list_id)
    tasks_tree.push(service, list_id)

def sync_todolist(path, profile, list_name):
    """Synchronizes the specified file with the specified todolist"""
    tree_remote = get_gtask_list_as_tasktree(profile, list_name)
    tree_org = parse_path(path)
    
    treemerge(tree_org, tree_remote)
    
    # write merged tree to tasklist
    service = get_service(profile)
    list_id = get_list_id(service, list_name)
    erase_todolist(profile, list_id)
    tree_org.push(service, list_id)
        
    # write merged tree to orgfile
    codecs.open(path, "w", "utf-8").write(str(tree_org))


def main():
    parser = argparse.ArgumentParser(description="Synchronize org-mode text" 
                                     "files with a google-tasks list.")
    
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--push", action='store_true',
            help='replace LISTNAME with the contents of FILE.')
    action.add_argument("--pull", action='store_true',
            help='replace FILE with the contents of LISTNAME.')
    action.add_argument("--sync", action='store_true',
            help='synchronize changes between FILE and LISTNAME.')
    
    parser.add_argument('--orgfile',
            metavar='FILE',
            help='An org-mode file to push from / pull to')
    # TODO: replace the --profile flag with a URL-like scheme for specifying
    # data sources. (e.g. using file:///path/to/orgfile or
    # gtasks://profile/listname, and having only --from and --to flags)
    parser.add_argument('--profile',
            default="__default",
            required=False,
            help='A user-defined profile name to distinguish between '
                 'different google accounts')
    parser.add_argument('--listname',
            help='A GTasks list to pull from / push to (default list if empty)')
    
    args = parser.parse_args()
    
    if args.push and not args.orgfile:
        parser.error('--orgfile must be specified when using --push')
    if args.sync and not args.orgfile:
        parser.error('--orgfile must be specified when using --sync')
    
    if args.pull:
        if args.orgfile is None:
            print_todolist(args.profile, args.listname)
        else:
            write_todolist(args.orgfile, args.profile, args.listname)
    elif args.push:
        if not os.path.exists(args.orgfile):
            print("The org-file you want to push does not exist.")
            sys.exit(2)
        push_todolist(args.orgfile, args.profile, args.listname)
    elif args.sync:
        if not os.path.exists(args.orgfile):
            print("The org-file you want to synchronize does not exist.")
            sys.exit(2)
        sync_todolist(args.orgfile, args.profile, args.listname)

if __name__ == "__main__":
    main()
