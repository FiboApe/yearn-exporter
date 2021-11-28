import logging
from functools import lru_cache

from brownie import Contract, chain, web3

from yearn.cache import memory
from yearn.exceptions import ArchiveNodeRequired
from yearn.networks import Network

logger = logging.getLogger(__name__)


def safe_views(abi):
    return [
        item["name"]
        for item in abi
        if item["type"] == "function"
        and item["stateMutability"] == "view"
        and not item["inputs"]
        and all(x["type"] in ["uint256", "bool"] for x in item["outputs"])
    ]


@memory.cache()
def get_block_timestamp(height):
    """
    An optimized variant of `chain[height].timestamp`
    """
    if chain.id == Network.Mainnet:
        header = web3.manager.request_blocking(f"erigon_getHeaderByNumber", [height])
        return int(header.timestamp, 16)
    elif chain.id == Network.Fantom:
        return chain[height].timestamp


@memory.cache()
def closest_block_after_timestamp(timestamp):
    logger.debug('closest block after timestamp %d', timestamp)
    height = chain.height
    lo, hi = 0, height

    while hi - lo > 1:
        mid = lo + (hi - lo) // 2
        if get_block_timestamp(mid) > timestamp:
            hi = mid
        else:
            lo = mid

    if get_block_timestamp(hi) < timestamp:
        raise IndexError('timestamp is in the future')

    return hi


def get_code(address, block=None):
    try:
        return web3.eth.get_code(address, block_identifier=block)
    except ValueError as exc:
        if 'missing trie node' in exc.args[0]['message']:
            raise ArchiveNodeRequired('querying historical state requires an archive node')
        raise exc


@memory.cache()
def contract_creation_block(address) -> int:
    """
    Find contract creation block using binary search.
    NOTE Requires access to historical state. Doesn't account for CREATE2 or SELFDESTRUCT.
    """
    logger.info("contract creation block %s", address)

    height = chain.height
    lo, hi = 0, height

    while hi - lo > 1:
        mid = lo + (hi - lo) // 2
        if get_code(address, block=mid):
            hi = mid
        else:
            lo = mid

    return hi if hi != height else None


class Singleton(type):
    def __init__(self, *args, **kwargs):
        self.__instance = None
        super().__init__(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        if self.__instance is None:
            self.__instance = super().__call__(*args, **kwargs)
            return self.__instance
        else:
            return self.__instance


# Contract instance singleton, saves about 20ms of init time
contract = lru_cache(maxsize=None)(Contract)

def is_contract(address: str) -> bool:
    '''checks to see if the input address is a contract'''
    return web3.eth.get_code(address) != '0x'
