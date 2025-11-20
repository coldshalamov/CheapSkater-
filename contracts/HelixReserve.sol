// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

import "./AlphaHelixToken.sol";

/**
 * @title HelixReserve
 * @notice Allows users to buy and sell HLX tokens at a fixed rate.
 */
contract HelixReserve is ReentrancyGuard {
    uint256 public constant EXCHANGE_RATE = 1000; // 1 ETH = 1000 HLX

    AlphaHelixToken public immutable token;

    constructor(AlphaHelixToken _token) {
        token = _token;
    }

    /**
     * @notice Buy HLX tokens with ETH at the fixed exchange rate.
     */
    function buy() public payable nonReentrant {
        require(msg.value > 0, "No ETH sent");

        uint256 hlxAmount = msg.value * EXCHANGE_RATE;
        token.mint(msg.sender, hlxAmount);
    }

    /**
     * @notice Sell HLX tokens in exchange for ETH at the fixed exchange rate.
     * @param hlxAmount Amount of HLX tokens to sell.
     */
    function sell(uint256 hlxAmount) external nonReentrant {
        require(hlxAmount > 0, "Amount must be greater than zero");

        uint256 ethAmount = hlxAmount / EXCHANGE_RATE;
        require(ethAmount > 0, "Amount too small");
        require(address(this).balance >= ethAmount, "Insufficient ETH reserve");

        token.burn(msg.sender, hlxAmount);

        (bool success, ) = payable(msg.sender).call{value: ethAmount}("");
        require(success, "ETH transfer failed");
    }

    receive() external payable {
        buy();
    }
}
