from celery import Celery
import logging


logger = logging.getLogger(__name__)


def get_celery_stats(agent):
    agent.run_event.wait()
    config = agent.pluginconfig['celery']
    try:
        logger.debug('try to create the database...')
        agent.create_database('celery')
        agent.create_retention_policy('celery_rp',
                                      '365d',
                                      '1',
                                      'celery')
        logger.info('database "%s" created successfully', 'celery')
    except:
        pass
    app = Celery(broker=config['broker'])
    state = app.events.State()

    def announce_failed_tasks(event):
        state.event(event)
        if 'uuid' in event:
            task = state.tasks.get(event['uuid'])
            # print('\nEVENT: {}'.format(event))

            if task.state in ['SUCCESS', 'FAILURE'] and task.name is not None:
                data = [{
                    'measurement': 'tasks',
                    'tags': {
                        'worker': task.worker.hostname,
                        'task_name': task.name,
                        'state': task.state,
                    },
                    'fields': {
                        'runtime': task.runtime if task.runtime else 0,
                        'timestamp': task.timestamp,
                        'started': task.started
                    }
                }]
                agent.push(data, 'celery')

    def worker_heartbeat(event):
        state.event(event)

        worker_name = event['hostname']
        inspect = app.control.inspect([])
        worker_stat = inspect.stats()[worker_name]

        # print('WORKER STATE: {}'.format(worker_stat))
        # print('\nEVENT: {}'.format(event))
        if 'active' in event and event['active'] > 0:
            data = [{
                'measurement': 'workers',
                'tags': {
                    'name': event['hostname'],
                    #'broker': broker
                    # 'pid': event['pid'],
                },
                'fields': {
                    'processed': event['processed'],
                    'timestamp': event['timestamp'],
                    'active': event['active'],
                    'mem': worker_stat['rusage']['maxrss'],
                }
            }]
            agent.push(data, 'celery')

    with app.connection() as connection:
        recv = app.events.Receiver(connection, handlers={
            'worker-heartbeat': worker_heartbeat,
            '*': announce_failed_tasks,
        })
        while agent.run_event.is_set():
            recv.capture(limit=config['limit'], timeout=None, wakeup=True)

    logger.debug('get_celery_stats exited')
