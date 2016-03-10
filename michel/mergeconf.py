#!/usr/bin/env python
# -*- coding: utf-8 -*-

import codecs
import re
import io
import datetime
import subprocess
import tempfile

from michel.utils import *

class InteractiveMergeConf:
    def __init__(self, adapter):
        self.adapter = adapter
        
                
    def is_needed(self, task_org):
        if hasattr(self.adapter, 'is_needed'):
            return self.adapter.is_needed(self.__is_needed, task_org)
        return self.__is_needed(task_org)

    def select_org_task(self, task_remote, tasks_org):
        if hasattr(self.adapter, 'select_org_task'):
            return self.adapter.select_org_task(self.__select_org_task, task_remote, tasks_org)
        return self.__select_org_task(task_remote, tasks_org)

    def merge_title(self, task_remote, task_org):
        if hasattr(self.adapter, 'merge_title'):
            return self.adapter.merge_title(self.__merge_title, task_remote, task_org)
        return self.__merge_title(task_remote, task_org)

    def merge_completed(self, task_remote, task_org):
        if hasattr(self.adapter, 'merge_completed'):
            return self.adapter.merge_completed(self.__merge_completed, task_remote, task_org)
        return self.__merge_completed(task_remote, task_org)

    def merge_closed_time(self, task_remote, task_org):
        if hasattr(self.adapter, 'merge_closed_time'):
            return self.adapter.merge_closed_time(self.__merge_closed_time, task_remote, task_org)
        return self.__merge_closed_time(task_remote, task_org)

    def merge_scheduled_start_time(self, task_remote, task_org):
        if hasattr(self.adapter, 'merge_scheduled_start_time'):
            return self.adapter.merge_scheduled_start_time(self.__merge_scheduled_start_time, task_remote, task_org)
        return self.__merge_scheduled_start_time(task_remote, task_org)

    def merge_scheduled_end_time(self, task_remote, task_org):
        if hasattr(self.adapter, 'merge_scheduled_end_time'):
            return self.adapter.merge_scheduled_end_time(self.__merge_scheduled_end_time, task_remote, task_org)
        return self.__merge_scheduled_end_time(task_remote, task_org)

    def merge_notes(self, task_remote, task_org):
        if hasattr(self.adapter, 'merge_notes'):
            return self.adapter.merge_notes(self.__merge_notes, task_remote, task_org)
        return self.__merge_notes(task_remote, task_org)
    

    def __is_needed(self, task_org):
        return True

    def __select_org_task(self, task_remote, tasks_org):        
        uprint("\"{0}\" has not exact mapping in your local org-tree.".format(task_remote.title))
        uprint("Please manualy choose necessary item:")
    
        while True:
            for i, v in enumerate(tasks_org):
                uprint("[{0}] {1}".format(i, v.title))
                uprint("[n] -- create new")
                uprint("[d] -- discard new")

                result = input()
                try:
                    if result == 'n':
                        return 'new'
                    if result == 'd':
                        return 'discard'

                    result = int(result)
                    if result >= 0 and result <= i:
                        return result
                except:
                    pass

        uprint("Incorrect input!")

    def __merge_title(self, task_remote, task_org):
        uprint("Tasks has different titles")
        uprint("Please manualy choose necessary value:")
        return self.__select_from([task_remote.title, task_org.title])

    def __merge_completed(self, task_remote, task_org):
        return task_remote.completed or task_org.completed

    def __merge_closed_time(self, task_remote, task_org):
        if task_remote.completed:
            if task_remote.closed_time and task_org.closed_time:
                return min(task_remote.closed_time,  task_org.closed_time)
            elif task_remote.closed_time or task_org.closed_time:
                return task_remote.closed_time or task_org.closed_time
            else:
                return datetime.datetime.now()
        else:
            return None

    def __merge_scheduled_start_time(self, task_remote, task_org):
        uprint("Task \"{0}\" has different values for attribute \"scheduled_start_time\"".format(task_remote.title))
        uprint("Please manualy choose necessary value:")
        return self.__select_from([task_remote.scheduled_start_time, task_org.scheduled_start_time])

    def __merge_scheduled_end_time(self, task_remote, task_org):
        uprint("Task \"{0}\" has different values for attribute \"scheduled_end_time\"".format(task_remote.title))
        uprint("Please manualy choose necessary value:")
        return self.__select_from([task_remote.scheduled_end_time, task_org.scheduled_end_time])

    def __merge_notes(self, task_remote, task_org):
        uprint("Task \"{0}\" has different values for attribute \"notes\"".format(task_remote.title))
        uprint("Please manualy choose necessary:")

        items = [task_remote.notes, task_org.notes]
        while True:
            for i, v in enumerate(items):
                uprint("[{0}] Use this block:".format(i))
                for line in v:
                    uprint(line)
                uprint("-------------------------------------")
        
            uprint("[e] Edit in external editor")
            
            result = input()
            try:
                if result == 'e':
                    break
                
                result = int(result)
                if result >= 0 and result <= i:
                    return items[result]
            except:
                pass

            uprint("Incorrect input!")

        # External editor
        temp_fid, temp_name = tempfile.mkstemp()
        try:
            with codecs.open(temp_name, "w", encoding="utf-8") as temp_file:
                for item in items:
                    for line in item:
                        temp_file.write(line)
                        temp_file.write('\n')
                    
            subprocess.call('vim -n {0}'.format(temp_name), shell=True)
            
            with codecs.open(temp_name, "r", encoding="utf-8") as temp_file:
                result = [x.strip() for x in temp_file.readlines()]
            
        except Exception as e:
            uprint(e)
            
        os.close(temp_fid)
        os.remove(temp_name)
        return result

    def __select_from(self, items):
        while True:
            for i, v in enumerate(items):
                uprint("[{0}] {1}".format(i, v))

            result = input()
            try:
                result = int(result)
                if result >= 0 and result <= i:
                    return items[result]
            except:
                pass

            uprint("Incorrect input!")
