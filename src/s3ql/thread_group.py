'''
thread_group.py - this file is part of S3QL (http://s3ql.googlecode.com)

Copyright (C) 2010 Nikolaus Rath <Nikolaus@rath.org>

This program can be distributed under the terms of the GNU LGPL.
'''

from __future__ import division, print_function, absolute_import

import threading
import sys
import logging
from .common import EmbeddedException

log = logging.getLogger("thread_group")

class Thread(threading.Thread):

    def __init__(self, group):
        super(Thread, self).__init__()

        self._exc = None
        self._tb = None
        self._joined = False
        self._group = group
    
    def run(self):
        try:
            try:
                self.run_protected()
            finally:
                log.debug('thread: waiting for lock')
                with self._group.lock:
                    log.debug('thread: calling notify()')
                    self._group.active_threads.remove(self)
                    self._group.finished_threads.append(self)
                    self._group.lock.notifyAll()
        except BaseException as exc:
            self._exc = exc
            self._tb = sys.exc_info()[2] # This creates a circular reference chain           

    def join_and_raise(self):
        '''Wait for the thread to finish, raise any occurred exceptions'''
        
        self._joined = True
        self.join()
        if self._exc is not None:
            # Break reference chain
            tb = self._tb
            del self._tb
            raise EmbeddedException(self._exc, tb, self.name)


    def __del__(self):
        if not self._joined:
            raise RuntimeError("Thread was destroyed without calling join_and_raise()!")



class ThreadGroup(object):
    '''Represents a group of threads.
    
    This class is threadsafe, instance methods can safely be
    called concurrently.'''
    
    def __init__(self, max_threads):
        '''Initialize thread group
        
        `max_active` specifies the maximum number of running threads
        in the group. 
        '''
        
        self.max_threads = max_threads
        self.active_threads = list()
        self.finished_threads = list()
        self.lock = threading.Condition(threading.RLock())
        
    def add(self, fn, max_threads=None, *a, **kw):
        '''Add new thread that runs given function
        
        This method waits until there are less than `max_threads` active
        threads, then it starts a new thread executing `fn`.
                
        If `max_threads` is `None`, the `max_threads` value passed
        to the constructor is used instead.
        '''
        
        if max_threads is None:
            max_threads = self.max_threads
            
        t = Thread(self)
        
        # Attribute defined outside init
        #pylint: disable-msg=W0201
        t.run_protected = lambda: fn(*a, **kw)
        
        with self.lock:
            while len(self) >= max_threads:
                self.join_one()
                
            self.active_threads.append(t)
            
        t.start()
    
    def join_one(self):
        '''Wait for any one thread to finish
        
        If the thread terminated with an exception, the exception
        is encapsulated in `EmbeddedException` and raised again. If there are
        no active threads, the call returns without doing anything.
                
        If more than one thread has called `join_one`, a single thread
        that finishes execution will cause all pending `join_one` calls
        to return.
        '''
        
        with self.lock:
            if len(self) == 0:
                return
            
            try:
                self.finished_threads.pop().join_and_raise()
            except IndexError:
                # Wait for thread to terminate
                log.debug('join_one: wait()')
                self.lock.wait()
            
    def join_all(self):
        '''Call join_one() until all threads have terminated'''
        
        with self.lock:
            while len(self) > 0: 
                self.join_one()    
                
    def __len__(self):
        with self.lock:
            return len(self.active_threads) + len(self.finished_threads)